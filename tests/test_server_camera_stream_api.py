import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import server_cameras


class FakeCameraManager:
    def __init__(self, running=True):
        self.running = running
        self.stream_calls = []
        self.start_calls = []

    def status(self, action=None):
        if action:
            return {"action": action, "running": self.running}
        return {
            "check_in": {"action": "check_in", "running": self.running},
            "check_out": {"action": "check_out", "running": self.running},
        }

    def mjpeg_stream(self, action):
        self.stream_calls.append(action)
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\njpeg\r\n"

    def start(self, action):
        self.start_calls.append(action)
        return {"action": action, "running": True, "source": "configured-source"}


class ServerCameraStreamApiTests(unittest.TestCase):
    def setUp(self):
        self.original_manager = server_cameras.server_camera_manager
        self.app = FastAPI()
        self.app.include_router(server_cameras.router)

    def tearDown(self):
        server_cameras.server_camera_manager = self.original_manager
        self.app.dependency_overrides.clear()

    def authorize_staff(self):
        self.app.dependency_overrides[
            server_cameras.require_admin_or_lab_manager
        ] = lambda: {"id": 1, "role": "admin"}

    def authorize_admin(self):
        self.app.dependency_overrides[server_cameras.require_admin] = lambda: {
            "id": 1,
            "role": "admin",
        }

    def test_stream_requires_an_authenticated_staff_session(self):
        server_cameras.server_camera_manager = FakeCameraManager()
        client = TestClient(self.app, base_url="http://127.0.0.1")

        response = client.get("/api/server-cameras/check_in/stream")

        self.assertEqual(response.status_code, 401)

    def test_stream_returns_authenticated_mjpeg_response(self):
        manager = FakeCameraManager()
        server_cameras.server_camera_manager = manager
        self.authorize_staff()
        client = TestClient(self.app, base_url="http://127.0.0.1")

        response = client.get("/api/server-cameras/check_in/stream")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.headers["content-type"].startswith(
                "multipart/x-mixed-replace; boundary=frame"
            )
        )
        self.assertIn("no-store", response.headers["cache-control"])
        self.assertIn(b"Content-Type: image/jpeg", response.content)
        self.assertEqual(manager.stream_calls, ["check_in"])

    def test_stream_rejects_camera_that_is_not_running(self):
        server_cameras.server_camera_manager = FakeCameraManager(running=False)
        self.authorize_staff()
        client = TestClient(self.app, base_url="http://127.0.0.1")

        response = client.get("/api/server-cameras/check_out/stream")

        self.assertEqual(response.status_code, 409)

    def test_start_uses_configured_source_without_request_body(self):
        manager = FakeCameraManager(running=False)
        server_cameras.server_camera_manager = manager
        self.authorize_admin()
        client = TestClient(self.app, base_url="http://127.0.0.1")

        response = client.post("/api/server-cameras/check_in/start")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(manager.start_calls, ["check_in"])
        self.assertEqual(response.json()["source"], "configured-source")

    def test_start_rejects_source_override_payload(self):
        manager = FakeCameraManager(running=False)
        server_cameras.server_camera_manager = manager
        self.authorize_admin()
        client = TestClient(self.app, base_url="http://127.0.0.1")

        response = client.post(
            "/api/server-cameras/check_in/start",
            json={"source": "untrusted-override"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(manager.start_calls, [])

    def test_long_lived_stream_stops_after_session_is_revoked(self):
        manager = FakeCameraManager()

        def two_frames(_action):
            yield b"first"
            yield b"second"

        manager.mjpeg_stream = two_frames
        server_cameras.server_camera_manager = manager
        actor = {"id": 1, "role": "admin", "status": "active"}

        with patch.object(
            server_cameras.time, "monotonic", side_effect=[0.0, 0.0, 6.0]
        ), patch.object(server_cameras, "user_from_session_token", return_value=None):
            chunks = list(
                server_cameras._authorized_camera_stream(
                    "check_in", "revoked-token", actor
                )
            )

        self.assertEqual(chunks, [b"first"])


if __name__ == "__main__":
    unittest.main()

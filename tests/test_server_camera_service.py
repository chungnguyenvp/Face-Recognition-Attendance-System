import unittest
from unittest.mock import patch

from app.services import realtime_session_service, server_camera_service
from app.services.server_camera_service import MJPEG_BOUNDARY, ServerCameraManager


class FakeThread:
    def __init__(self, alive: bool):
        self.alive = alive
        self.join_timeouts = []

    def is_alive(self):
        return self.alive

    def join(self, timeout=None):
        self.join_timeouts.append(timeout)


class FakeStartThread:
    def __init__(self, target, args, name, daemon):
        self.target = target
        self.args = args
        self.name = name
        self.daemon = daemon
        self.started = False

    def start(self):
        self.started = True

    def is_alive(self):
        return self.started


class ServerCameraManagerTests(unittest.TestCase):
    def setUp(self):
        realtime_session_service._presence_sessions.clear()

    def test_stop_keeps_runtime_running_while_worker_is_still_alive(self):
        manager = ServerCameraManager()
        worker = FakeThread(alive=True)
        runtime = manager._cameras["check_in"]
        runtime.running = True
        runtime.connected = True
        runtime.thread = worker

        status = manager.stop("check_in")

        self.assertEqual(worker.join_timeouts, [3])
        self.assertTrue(status["running"])
        self.assertFalse(status["connected"])
        self.assertEqual(status["last_error"], "Camera worker is still stopping.")
        self.assertIs(runtime.thread, worker)

    def test_stop_clears_runtime_after_worker_has_stopped(self):
        manager = ServerCameraManager()
        worker = FakeThread(alive=False)
        runtime = manager._cameras["check_out"]
        runtime.running = True
        runtime.connected = True
        runtime.thread = worker

        status = manager.stop("check_out")

        self.assertFalse(status["running"])
        self.assertFalse(status["connected"])
        self.assertIsNone(runtime.thread)

    def test_start_assigns_a_unique_scope_to_each_camera_runtime(self):
        first = ServerCameraManager()
        second = ServerCameraManager()

        with patch(
            "app.services.server_camera_service.threading.Thread",
            FakeStartThread,
        ):
            first.start("check_in", "0")
            second.start("check_in", "0")

        first_scope = first._cameras["check_in"].session_scope
        second_scope = second._cameras["check_in"].session_scope
        self.assertTrue(first_scope.startswith("server-camera:check_in:"))
        self.assertTrue(second_scope.startswith("server-camera:check_in:"))
        self.assertNotEqual(first_scope, second_scope)

    def test_stop_clears_sessions_owned_by_camera_scope(self):
        manager = ServerCameraManager()
        worker = FakeThread(alive=False)
        runtime = manager._cameras["check_in"]
        runtime.running = True
        runtime.thread = worker
        runtime.session_scope = "server-camera:check_in:test"
        realtime_session_service.session_decision(
            "check_in",
            {
                "recognized": True,
                "student_id": 7,
                "bbox": [0, 0, 100, 100],
                "liveness_status": "live",
                "liveness": {"real_score": 0.9},
                "quality": {"ok": True},
            },
            runtime.session_scope,
        )

        manager.stop("check_in")

        self.assertFalse(realtime_session_service._presence_sessions)
        self.assertIsNone(runtime.session_scope)

    def test_mjpeg_stream_publishes_latest_frame_without_opening_camera(self):
        manager = ServerCameraManager()
        runtime = manager._cameras["check_in"]
        runtime.running = True
        frame = type("Frame", (), {"shape": (360, 640, 3)})()

        sequence = manager._publish_preview("check_in", frame, b"jpeg-data")
        stream = manager.mjpeg_stream("check_in")
        chunk = next(stream)
        stream.close()

        self.assertEqual(sequence, 1)
        self.assertIn(f"--{MJPEG_BOUNDARY}\r\n".encode(), chunk)
        self.assertIn(b"Content-Type: image/jpeg", chunk)
        self.assertIn(b"X-Frame-Sequence: 1", chunk)
        self.assertTrue(chunk.endswith(b"jpeg-data\r\n"))
        self.assertEqual(runtime.frame_width, 640)
        self.assertEqual(runtime.frame_height, 360)

    def test_status_exposes_frame_metadata_but_not_jpeg_bytes(self):
        manager = ServerCameraManager()
        runtime = manager._cameras["check_out"]
        runtime.running = True
        frame = type("Frame", (), {"shape": (720, 1280, 3)})()
        manager._publish_preview("check_out", frame, b"private-jpeg")

        status = manager.status("check_out")

        self.assertEqual(status["frame_width"], 1280)
        self.assertEqual(status["frame_height"], 720)
        self.assertEqual(status["frame_sequence"], 1)
        self.assertNotIn("latest_jpeg", status)
        self.assertNotIn(b"private-jpeg", status.values())

    def test_status_redacts_camera_source_credentials(self):
        manager = ServerCameraManager()
        manager._cameras["check_in"].source = (
            "rtsp://camera-user:camera-password@192.168.1.50:554/stream1?token=secret"
        )

        source = manager.status("check_in")["source"]

        self.assertEqual(source, "rtsp://***@192.168.1.50:554/stream1")
        self.assertNotIn("camera-password", source)
        self.assertNotIn("secret", source)

    def test_configured_sources_come_only_from_environment_settings(self):
        manager = ServerCameraManager()

        with patch.object(server_camera_service.settings, "check_in_camera_source", " 1 "), patch.object(
            server_camera_service.settings,
            "check_out_camera_source",
            "rtsp://camera.local/stream",
        ):
            self.assertEqual(manager.configured_source("check_in"), "1")
            self.assertEqual(
                manager.configured_source("check_out"),
                "rtsp://camera.local/stream",
            )

    def test_auto_start_comes_only_from_environment_settings(self):
        manager = ServerCameraManager()

        with patch.object(server_camera_service.settings, "auto_start_cameras", True):
            self.assertTrue(manager.auto_start_enabled())
        with patch.object(server_camera_service.settings, "auto_start_cameras", False):
            self.assertFalse(manager.auto_start_enabled())


if __name__ == "__main__":
    unittest.main()

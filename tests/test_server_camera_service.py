import unittest
from unittest.mock import patch

from app.services import realtime_session_service
from app.services.server_camera_service import ServerCameraManager


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


if __name__ == "__main__":
    unittest.main()

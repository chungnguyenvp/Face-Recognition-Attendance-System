import unittest

from app.services.server_camera_service import ServerCameraManager


class FakeThread:
    def __init__(self, alive: bool):
        self.alive = alive
        self.join_timeouts = []

    def is_alive(self):
        return self.alive

    def join(self, timeout=None):
        self.join_timeouts.append(timeout)


class ServerCameraManagerTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()

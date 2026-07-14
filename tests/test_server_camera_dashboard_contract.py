import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ServerCameraDashboardContractTests(unittest.TestCase):
    def test_dashboard_contains_backend_stream_targets_and_overlays(self):
        template = (PROJECT_ROOT / "web/templates/dashboard.html").read_text(
            encoding="utf-8"
        )

        self.assertIn('id="checkInServerStream"', template)
        self.assertIn('id="checkOutServerStream"', template)
        self.assertIn('id="checkInOverlay"', template)
        self.assertIn('id="checkOutOverlay"', template)

    def test_server_mode_uses_mjpeg_status_and_control_apis(self):
        javascript = (
            PROJECT_ROOT / "web/static/js/app-settings-realtime.js"
        ).read_text(encoding="utf-8")

        self.assertIn("realtime_camera_mode", javascript)
        self.assertIn("/api/server-cameras/status", javascript)
        self.assertIn("/api/server-cameras/${action}/stream", javascript)
        self.assertIn("/api/server-cameras/${action}/start", javascript)
        self.assertIn("/api/server-cameras/${action}/stop", javascript)
        self.assertIn("/api/server-cameras/stop-all", javascript)


if __name__ == "__main__":
    unittest.main()

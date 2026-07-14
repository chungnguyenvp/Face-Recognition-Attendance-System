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

    def test_dashboard_uses_only_server_camera_apis(self):
        javascript = (
            PROJECT_ROOT / "web/static/js/app-settings-realtime.js"
        ).read_text(encoding="utf-8")

        self.assertIn("/api/server-cameras/status", javascript)
        self.assertIn("/api/server-cameras/${action}/stream", javascript)
        self.assertIn("/api/server-cameras/${action}/start", javascript)
        self.assertIn("/api/server-cameras/${action}/stop", javascript)
        self.assertIn("/api/server-cameras/stop-all", javascript)
        self.assertNotIn("new WebSocket", javascript)
        self.assertNotIn("getUserMedia", javascript)

    def test_dashboard_has_no_browser_attendance_camera_settings(self):
        template = (PROJECT_ROOT / "web/templates/dashboard.html").read_text(
            encoding="utf-8"
        )

        self.assertNotIn('id="checkInVideo"', template)
        self.assertNotIn('id="checkOutVideo"', template)
        self.assertNotIn('id="settingCheckInCamera"', template)
        self.assertNotIn('id="settingCheckOutCamera"', template)
        self.assertNotIn('id="settingCheckInCameraSource"', template)
        self.assertNotIn('id="settingCheckOutCameraSource"', template)


if __name__ == "__main__":
    unittest.main()

import unittest


class AppSecurityHeadersTests(unittest.TestCase):
    def setUp(self):
        try:
            from fastapi.testclient import TestClient
            from app.main import app
        except ModuleNotFoundError as exc:
            self.skipTest(f"{exc.name} is not installed in this test environment.")

        self.client = TestClient(app, base_url="http://127.0.0.1")

    def test_security_headers_are_present_without_hsts_on_http(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["Referrer-Policy"], "strict-origin-when-cross-origin")
        self.assertIn("camera=(self)", response.headers["Permissions-Policy"])
        self.assertNotIn("Strict-Transport-Security", response.headers)

    def test_health_hides_internal_details_by_default(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})

    def test_docs_and_openapi_are_not_public_by_default(self):
        self.assertEqual(self.client.get("/docs").status_code, 404)
        self.assertEqual(self.client.get("/redoc").status_code, 404)
        self.assertEqual(self.client.get("/openapi.json").status_code, 404)

    def test_untrusted_host_is_rejected(self):
        response = self.client.get("/health", headers={"host": "evil.example"})

        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()

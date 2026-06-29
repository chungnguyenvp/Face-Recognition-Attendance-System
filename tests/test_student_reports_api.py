import tempfile
import unittest
from pathlib import Path


class StudentReportsApiTests(unittest.TestCase):
    def setUp(self):
        try:
            from fastapi.testclient import TestClient
            from app import db as db_module
            from app.core import security
            from app.main import app
            from app.services import private_storage
        except ModuleNotFoundError as exc:
            self.skipTest(f"{exc.name} is not installed in this test environment.")

        self.TestClient = TestClient
        self.db_module = db_module
        self.security = security
        self.private_storage = private_storage
        self.app = app
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_database_path = db_module.settings.database_path
        self.original_iterations = security.settings.password_pbkdf2_iterations
        self.original_admin_username = db_module.settings.default_admin_username
        self.original_admin_password = db_module.settings.default_admin_password
        self.original_storage_root = private_storage.PRIVATE_STORAGE_ROOT
        self.original_report_dir = private_storage.PRIVATE_REPORT_DIR
        private_storage.PRIVATE_STORAGE_ROOT = Path(self.temp_dir.name) / "private"
        private_storage.PRIVATE_REPORT_DIR = private_storage.PRIVATE_STORAGE_ROOT / "student_reports"
        db_module.settings.database_path = str(Path(self.temp_dir.name) / "reports_api.db")
        security.settings.password_pbkdf2_iterations = 1_000
        db_module.settings.default_admin_username = "admin"
        db_module.settings.default_admin_password = "admin123"
        db_module.init_db()

        self.admin = self.login_client("admin", "admin123")
        self.student_one_id = self.create_student("REPORT001", "Student One")
        self.student_two_id = self.create_student("REPORT002", "Student Two")
        self.create_user("report-student-one", "student123", "student", self.student_one_id)
        self.create_user("report-student-two", "student123", "student", self.student_two_id)
        self.manager_one = self.create_user("report-manager-one", "manager123", "lab_manager")
        self.manager_two = self.create_user("report-manager-two", "manager123", "lab_manager")
        self.student_one = self.login_client("report-student-one", "student123")
        self.student_two = self.login_client("report-student-two", "student123")
        self.manager_one_client = self.login_client("report-manager-one", "manager123")
        self.manager_two_client = self.login_client("report-manager-two", "manager123")

    def tearDown(self):
        if hasattr(self, "db_module"):
            self.db_module.settings.database_path = self.original_database_path
            self.security.settings.password_pbkdf2_iterations = self.original_iterations
            self.db_module.settings.default_admin_username = self.original_admin_username
            self.db_module.settings.default_admin_password = self.original_admin_password
            self.private_storage.PRIVATE_STORAGE_ROOT = self.original_storage_root
            self.private_storage.PRIVATE_REPORT_DIR = self.original_report_dir
        if hasattr(self, "temp_dir"):
            self.temp_dir.cleanup()

    def csrf_headers(self, client):
        return {"X-CSRF-Token": client.cookies.get("csrf_token", "")}

    def login_client(self, username, password):
        client = self.TestClient(self.app, base_url="http://127.0.0.1")
        response = client.post("/api/auth/login", json={"username": username, "password": password})
        self.assertEqual(response.status_code, 200, response.text)
        return client

    def create_student(self, code, name):
        response = self.admin.post(
            "/api/students", json={"student_code": code, "full_name": name, "status": "active"},
            headers=self.csrf_headers(self.admin),
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["id"]

    def create_user(self, username, password, role, student_id=None):
        response = self.admin.post(
            "/api/users", json={"username": username, "password": password, "role": role, "student_id": student_id},
            headers=self.csrf_headers(self.admin),
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["item"]

    def submit_report(self):
        response = self.student_one.post(
            "/api/student/reports",
            data={
                "title": "Bao cao tuan 3", "report_type": "weekly", "description": "Da hoan thanh phan dang nhap.",
                "reviewer_id": str(self.manager_one["id"]),
            },
            files={"attachment": ("bao_cao.pdf", b"%PDF-1.4\nreport", "application/pdf")},
            headers=self.csrf_headers(self.student_one),
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["item"]

    def test_submission_is_private_to_assigned_lab_manager_and_preserves_versions(self):
        report = self.submit_report()
        report_id = report["id"]
        self.assertEqual(report["status"], "submitted")
        self.assertEqual(report["reviewer_id"], self.manager_one["id"])
        self.assertEqual(report["current_version"], 1)

        self.assertEqual(self.student_two.get(f"/api/student/reports/{report_id}").status_code, 403)
        self.assertEqual(self.manager_two_client.get(f"/api/reports/{report_id}").status_code, 403)
        self.assertEqual(self.manager_two_client.get("/api/reports").json()["count"], 0)

        detail = self.manager_one_client.get(f"/api/reports/{report_id}")
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertIsNotNone(detail.json()["item"]["current_viewed_at"])

        missing_comment = self.manager_one_client.post(
            f"/api/reports/{report_id}/review", json={"status": "revision_requested", "comment": ""},
            headers=self.csrf_headers(self.manager_one_client),
        )
        self.assertEqual(missing_comment.status_code, 409)
        review = self.manager_one_client.post(
            f"/api/reports/{report_id}/review", json={"status": "revision_requested", "comment": "Bo sung anh ket qua test."},
            headers=self.csrf_headers(self.manager_one_client),
        )
        self.assertEqual(review.status_code, 200, review.text)
        self.assertEqual(review.json()["item"]["status"], "revision_requested")

        resubmitted = self.student_one.post(
            f"/api/student/reports/{report_id}/resubmit",
            data={"description": "Da bo sung anh test."},
            files={"attachment": ("bao_cao_v2.pdf", b"%PDF-1.4\nreport-v2", "application/pdf")},
            headers=self.csrf_headers(self.student_one),
        )
        self.assertEqual(resubmitted.status_code, 200, resubmitted.text)
        item = resubmitted.json()["item"]
        self.assertEqual(item["status"], "submitted")
        self.assertEqual(item["current_version"], 2)
        self.assertEqual([version["version_no"] for version in item["versions"]], [2, 1])

        original_download = self.student_one.get(f"/api/student/reports/{report_id}/versions/1/download")
        self.assertEqual(original_download.status_code, 200)
        self.assertEqual(original_download.content, b"%PDF-1.4\nreport")

        approved = self.manager_one_client.post(
            f"/api/reports/{report_id}/review", json={"status": "approved", "comment": "Dat yeu cau."},
            headers=self.csrf_headers(self.manager_one_client),
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["item"]["status"], "approved")

        audit = self.admin.get("/api/audit-logs?entity_type=student_report")
        self.assertEqual(audit.status_code, 200, audit.text)
        self.assertTrue(any(item["action"] == "student_reports.resubmit" for item in audit.json()["items"]))

    def test_admin_can_see_all_reports_but_student_cannot_review(self):
        report = self.submit_report()
        report_id = report["id"]
        admin_list = self.admin.get("/api/reports")
        self.assertEqual(admin_list.status_code, 200, admin_list.text)
        self.assertEqual(admin_list.json()["count"], 1)
        self.assertEqual(self.student_one.post(
            f"/api/reports/{report_id}/review", json={"status": "approved"}, headers=self.csrf_headers(self.student_one)
        ).status_code, 403)


if __name__ == "__main__":
    unittest.main()

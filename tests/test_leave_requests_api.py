import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path


class LeaveRequestsApiTests(unittest.TestCase):
    def setUp(self):
        try:
            from fastapi.testclient import TestClient
            from app import db as db_module
            from app.core import security
            from app.main import app
        except ModuleNotFoundError as exc:
            self.skipTest(f"{exc.name} is not installed in this test environment.")

        self.TestClient = TestClient
        self.db_module = db_module
        self.security = security
        self.app = app
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_database_path = db_module.settings.database_path
        self.original_iterations = security.settings.password_pbkdf2_iterations
        self.original_admin_username = db_module.settings.default_admin_username
        self.original_admin_password = db_module.settings.default_admin_password
        db_module.settings.database_path = str(Path(self.temp_dir.name) / "leave_requests_api.db")
        security.settings.password_pbkdf2_iterations = 1_000
        db_module.settings.default_admin_username = "admin"
        db_module.settings.default_admin_password = "admin123"
        db_module.init_db()

        self.admin = self.login_client("admin", "admin123")
        self.student_one_id = self.create_student("LEAVE001", "Student One")
        self.student_two_id = self.create_student("LEAVE002", "Student Two")
        self.create_user("leave-student-one", "student123", "student", self.student_one_id)
        self.create_user("leave-student-two", "student123", "student", self.student_two_id)
        self.create_user("leave-manager", "manager123", "lab_manager")
        self.student_one = self.login_client("leave-student-one", "student123")
        self.student_two = self.login_client("leave-student-two", "student123")
        self.manager = self.login_client("leave-manager", "manager123")
        self.leave_day = (date.today() + timedelta(days=2)).isoformat()

    def tearDown(self):
        if hasattr(self, "db_module"):
            self.db_module.settings.database_path = self.original_database_path
            self.security.settings.password_pbkdf2_iterations = self.original_iterations
            self.db_module.settings.default_admin_username = self.original_admin_username
            self.db_module.settings.default_admin_password = self.original_admin_password
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
            "/api/students",
            json={"student_code": code, "full_name": name, "status": "active"},
            headers=self.csrf_headers(self.admin),
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["id"]

    def create_user(self, username, password, role, student_id=None):
        response = self.admin.post(
            "/api/users",
            json={"username": username, "password": password, "role": role, "student_id": student_id},
            headers=self.csrf_headers(self.admin),
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["item"]

    def create_leave(self, client=None, reason="Em bi om can nghi de dieu tri."):
        client = client or self.student_one
        response = client.post(
            "/api/student/leave-requests",
            json={"leave_type": "sick", "start_date": self.leave_day, "end_date": self.leave_day, "reason": reason},
            headers=self.csrf_headers(client),
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["item"]

    def test_student_can_create_leave_request_and_csrf_is_required(self):
        missing_csrf = self.student_one.post(
            "/api/student/leave-requests",
            json={"leave_type": "sick", "start_date": self.leave_day, "end_date": self.leave_day, "reason": "Em bi om can nghi de dieu tri."},
        )
        self.assertEqual(missing_csrf.status_code, 403)

        item = self.create_leave()
        self.assertEqual(item["status"], "pending")
        self.assertEqual(item["student_id"], self.student_one_id)

    def test_student_cannot_view_or_cancel_another_students_request(self):
        item = self.create_leave()
        response = self.student_two.get(f"/api/student/leave-requests/{item['id']}")
        self.assertEqual(response.status_code, 403)
        response = self.student_two.patch(
            f"/api/student/leave-requests/{item['id']}/cancel",
            headers=self.csrf_headers(self.student_two),
        )
        self.assertEqual(response.status_code, 403)

    def test_student_can_cancel_own_pending_request(self):
        item = self.create_leave()
        response = self.student_one.patch(
            f"/api/student/leave-requests/{item['id']}/cancel",
            headers=self.csrf_headers(self.student_one),
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["item"]["status"], "cancelled")

    def test_lab_manager_can_approve_and_reject_pending_requests(self):
        first = self.create_leave()
        response = self.manager.patch(
            f"/api/leave-requests/{first['id']}/approve",
            json={"reviewer_note": "Da kiem tra."},
            headers=self.csrf_headers(self.manager),
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["item"]["status"], "approved")

        second_day = (date.today() + timedelta(days=4)).isoformat()
        response = self.student_one.post(
            "/api/student/leave-requests",
            json={"leave_type": "personal", "start_date": second_day, "end_date": second_day, "reason": "Can xu ly viec ca nhan."},
            headers=self.csrf_headers(self.student_one),
        )
        self.assertEqual(response.status_code, 200, response.text)
        second = response.json()["item"]
        response = self.manager.patch(
            f"/api/leave-requests/{second['id']}/reject",
            json={"reviewer_note": "Don gui qua sat ngay."},
            headers=self.csrf_headers(self.manager),
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["item"]["status"], "rejected")

    def test_admin_can_revoke_and_attendance_is_recalculated(self):
        item = self.create_leave()
        approved = self.manager.patch(
            f"/api/leave-requests/{item['id']}/approve",
            json={},
            headers=self.csrf_headers(self.manager),
        )
        self.assertEqual(approved.status_code, 200, approved.text)

        attendance = self.student_one.get(
            f"/api/student/attendance-records?date_from={self.leave_day}&date_to={self.leave_day}"
        )
        self.assertEqual(attendance.status_code, 200, attendance.text)
        self.assertEqual(attendance.json()["items"][0]["status"], "leave_approved")

        revoked = self.admin.patch(
            f"/api/leave-requests/{item['id']}/revoke",
            json={"reviewer_note": "Duyet nham, can thu hoi."},
            headers=self.csrf_headers(self.admin),
        )
        self.assertEqual(revoked.status_code, 200, revoked.text)
        self.assertEqual(revoked.json()["item"]["status"], "revoked")

        audit = self.admin.get("/api/audit-logs?entity_type=leave_request")
        self.assertEqual(audit.status_code, 200, audit.text)
        latest = audit.json()["items"][0]
        self.assertEqual(latest["action"], "leave_requests.revoke")
        self.assertEqual(
            json.loads(latest["details_json"]),
            {
                "end_date": self.leave_day,
                "leave_type": "sick",
                "reviewer_note": "Duyet nham, can thu hoi.",
                "start_date": self.leave_day,
                "status": "revoked",
            },
        )

        attendance = self.student_one.get(
            f"/api/student/attendance-records?date_from={self.leave_day}&date_to={self.leave_day}"
        )
        self.assertEqual(attendance.json()["items"][0]["status"], "pending")

    def test_staff_routes_enforce_roles_and_pending_transition(self):
        item = self.create_leave()
        response = self.student_one.get("/api/leave-requests")
        self.assertEqual(response.status_code, 403)

        response = self.manager.patch(
            f"/api/leave-requests/{item['id']}/revoke",
            json={"reviewer_note": "Khong duoc phep."},
            headers=self.csrf_headers(self.manager),
        )
        self.assertEqual(response.status_code, 403)

        approved = self.manager.patch(
            f"/api/leave-requests/{item['id']}/approve",
            json={},
            headers=self.csrf_headers(self.manager),
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        repeated = self.manager.patch(
            f"/api/leave-requests/{item['id']}/approve",
            json={},
            headers=self.csrf_headers(self.manager),
        )
        self.assertEqual(repeated.status_code, 409)


if __name__ == "__main__":
    unittest.main()

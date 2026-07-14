import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path


class OperationalSmokeTests(unittest.TestCase):
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
        self.original_health_details_enabled = db_module.settings.health_details_enabled
        self.original_public_docs_enabled = db_module.settings.public_docs_enabled
        self.original_default_admin_username = db_module.settings.default_admin_username
        self.original_default_admin_password = db_module.settings.default_admin_password
        db_module.settings.database_path = str(Path(self.temp_dir.name) / "operational_smoke.db")
        db_module.settings.password_pbkdf2_iterations = 1_000
        db_module.settings.health_details_enabled = False
        db_module.settings.public_docs_enabled = False
        db_module.settings.default_admin_username = "admin"
        db_module.settings.default_admin_password = "admin123"
        db_module.init_db()

    def tearDown(self):
        if hasattr(self, "db_module"):
            self.db_module.settings.database_path = self.original_database_path
            self.db_module.settings.password_pbkdf2_iterations = self.original_iterations
            self.db_module.settings.health_details_enabled = self.original_health_details_enabled
            self.db_module.settings.public_docs_enabled = self.original_public_docs_enabled
            self.db_module.settings.default_admin_username = self.original_default_admin_username
            self.db_module.settings.default_admin_password = self.original_default_admin_password
        if hasattr(self, "temp_dir"):
            self.temp_dir.cleanup()

    def client(self):
        return self.TestClient(self.app, base_url="http://127.0.0.1")

    def csrf_headers(self, client):
        return {"X-CSRF-Token": client.cookies.get("csrf_token", "")}

    def login(self, client, username="admin", password="admin123"):
        response = client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("session_token", client.cookies)
        self.assertIn("csrf_token", client.cookies)
        return response.json()

    def create_student(self, client, code="SV001", name="Nguyen Van A"):
        response = client.post(
            "/api/students",
            json={"student_code": code, "full_name": name, "class_name": "CNTT", "status": "active"},
            headers=self.csrf_headers(client),
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["id"]

    def create_user(self, client, username, password, role, student_id=None):
        payload = {"username": username, "password": password, "role": role, "student_id": student_id}
        response = client.post("/api/users", json=payload, headers=self.csrf_headers(client))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["item"]

    def test_admin_student_settings_dashboard_and_auth_flow(self):
        client = self.client()

        health = client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json(), {"ok": True})

        self.assertEqual(client.get("/api/dashboard").status_code, 401)
        self.login(client)

        self.assertEqual(client.get("/").status_code, 200)
        self.assertEqual(client.get("/api/auth/me").json()["user"]["role"], "admin")

        student_id = self.create_student(client, "  SV001  ", "  Nguyen Van A  ")
        duplicate = client.post(
            "/api/students",
            json={"student_code": "SV001", "full_name": "Duplicate", "status": "active"},
            headers=self.csrf_headers(client),
        )
        self.assertEqual(duplicate.status_code, 400)
        self.assertTrue(duplicate.json()["detail"])

        students = client.get("/api/students").json()["items"]
        self.assertEqual(len(students), 1)
        self.assertEqual(students[0]["student_code"], "SV001")
        self.assertEqual(students[0]["full_name"], "Nguyen Van A")

        work_time = client.put(
            f"/api/students/{student_id}/work-time",
            json={"work_start_time": "07:30", "work_end_time": "16:45"},
            headers=self.csrf_headers(client),
        )
        self.assertEqual(work_time.status_code, 200, work_time.text)
        updated_student = client.get("/api/students").json()["items"][0]
        self.assertEqual(updated_student["work_start_time"], "07:30")
        self.assertEqual(updated_student["work_end_time"], "16:45")

        settings_update = client.put(
            "/api/settings",
            json={
                "face_threshold": 0.6,
                "check_cooldown_seconds": 15,
                "frame_skip": 3,
                "missing_checkout_cutoff_time": "22:00",
                "work_start_time": "07:30",
                "work_end_time": "16:45",
                "late_grace_minutes": 10,
                "early_leave_grace_minutes": 15,
            },
            headers=self.csrf_headers(client),
        )
        self.assertEqual(settings_update.status_code, 200, settings_update.text)
        settings = client.get("/api/settings").json()
        self.assertEqual(settings["face_threshold"], "0.6")
        self.assertEqual(settings["missing_checkout_cutoff_time"], "22:00")

        dashboard = client.get("/api/dashboard")
        self.assertEqual(dashboard.status_code, 200, dashboard.text)
        stats = dashboard.json()["stats"]
        self.assertEqual(stats["total_students"], 1)
        self.assertEqual(stats["active_students"], 1)

    def test_role_boundaries_and_student_portal_flow(self):
        admin = self.client()
        self.login(admin)
        student_id = self.create_student(admin, "SV002", "Tran Thi B")
        self.create_user(admin, "student002", "student123", "student", student_id)
        self.create_user(admin, "labmanager", "manager123", "lab_manager")

        student = self.client()
        student_login = self.login(student, "student002", "student123")
        self.assertEqual(student_login["user"]["role"], "student")
        self.assertEqual(student.get("/").status_code, 200)
        self.assertEqual(student.get("/api/students").status_code, 403)
        student_profile = student.get("/api/student/me")
        self.assertEqual(student_profile.status_code, 200, student_profile.text)
        self.assertEqual(student_profile.json()["student"]["student_code"], "SV002")
        self.assertEqual(student.get("/api/student/faces").json()["count"], 0)

        lab_manager = self.client()
        self.login(lab_manager, "labmanager", "manager123")
        forbidden_admin_create = lab_manager.post(
            "/api/users",
            json={"username": "bad-admin", "password": "admin123", "role": "admin"},
            headers=self.csrf_headers(lab_manager),
        )
        self.assertEqual(forbidden_admin_create.status_code, 403)

        lab_student_id = self.create_student(lab_manager, "SV003", "Le Van C")
        lab_student_user = self.create_user(
            lab_manager,
            "student003",
            "student123",
            "student",
            lab_student_id,
        )
        users = lab_manager.get("/api/users").json()["items"]
        self.assertTrue(users)
        self.assertTrue(all(user["role"] == "student" for user in users))

        lock_student = lab_manager.put(
            f"/api/users/{lab_student_user['id']}",
            json={"status": "inactive"},
            headers=self.csrf_headers(lab_manager),
        )
        self.assertEqual(lock_student.status_code, 200, lock_student.text)

        locked_student = self.client()
        locked_login = locked_student.post(
            "/api/auth/login",
            json={"username": "student003", "password": "student123"},
        )
        self.assertEqual(locked_login.status_code, 403)

    def test_admin_can_manage_work_schedule(self):
        client = self.client()
        self.login(client)
        today = date.today().isoformat()
        schedule = client.put(
            "/api/work-schedule/settings",
            json={
                "effective_from": today,
                "monday_enabled": True,
                "tuesday_enabled": True,
                "wednesday_enabled": True,
                "thursday_enabled": True,
                "friday_enabled": True,
                "saturday_enabled": False,
                "sunday_enabled": False,
                "start_time": "08:00",
                "end_time": "17:00",
                "late_allowed_minutes": 5,
                "early_leave_allowed_minutes": 10,
                "checkout_cutoff_time": "20:00",
            },
            headers=self.csrf_headers(client),
        )
        self.assertEqual(schedule.status_code, 200, schedule.text)
        self.assertEqual(client.get("/api/work-schedule/settings").json()["saturday_enabled"], 0)

        holiday_date = (date.today() + timedelta(days=2)).isoformat()
        created = client.post(
            "/api/work-schedule/exceptions",
            json={"exception_date": holiday_date, "exception_type": "off", "holiday_name": "Nghỉ kiểm tra", "note": "Nghỉ toàn lab"},
            headers=self.csrf_headers(client),
        )
        self.assertEqual(created.status_code, 200, created.text)
        exception_id = created.json()["item"]["id"]
        calendar = client.get(f"/api/work-schedule/calendar?year={date.today().year}&month={date.today().month}")
        self.assertEqual(calendar.status_code, 200, calendar.text)
        self.assertTrue(calendar.json()["days"])
        deleted = client.delete(f"/api/work-schedule/exceptions/{exception_id}", headers=self.csrf_headers(client))
        self.assertEqual(deleted.status_code, 200, deleted.text)

    def test_deleting_student_deactivates_linked_user_and_revokes_session(self):
        admin = self.client()
        self.login(admin)
        student_id = self.create_student(admin, "SV-DELETE", "Delete Student")
        student_user = self.create_user(
            admin,
            "student-delete",
            "student123",
            "student",
            student_id,
        )

        student_client = self.client()
        self.login(student_client, "student-delete", "student123")

        response = admin.delete(
            f"/api/students/{student_id}",
            headers=self.csrf_headers(admin),
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["linked_user_deactivated"])

        with self.db_module.get_db() as db:
            deleted_student = db.execute(
                "SELECT id FROM students WHERE id=?",
                (student_id,),
            ).fetchone()
            user = db.execute(
                "SELECT student_id, status FROM users WHERE id=?",
                (student_user["id"],),
            ).fetchone()
            active_sessions = db.execute(
                """
                SELECT COUNT(*)
                FROM user_sessions
                WHERE user_id=? AND revoked_at IS NULL
                """,
                (student_user["id"],),
            ).fetchone()[0]

        self.assertIsNone(deleted_student)
        self.assertIsNone(user["student_id"])
        self.assertEqual(user["status"], "inactive")
        self.assertEqual(active_sessions, 0)
        self.assertEqual(student_client.get("/api/auth/me").status_code, 401)


if __name__ == "__main__":
    unittest.main()

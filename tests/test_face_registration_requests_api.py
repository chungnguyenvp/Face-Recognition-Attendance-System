import itertools
import tempfile
import unittest
from pathlib import Path


class FaceRegistrationRequestsApiTests(unittest.TestCase):
    def setUp(self):
        try:
            import numpy as np
            from fastapi.testclient import TestClient
            from app import db as db_module
            from app.core import security
            from app.main import app
            import app.routers.face_registration_requests as request_router
            import app.services.face_registration_request_service as request_service
        except ModuleNotFoundError as exc:
            self.skipTest(f"{exc.name} is not installed in this test environment.")

        self.np = np
        self.TestClient = TestClient
        self.db_module = db_module
        self.security = security
        self.app = app
        self.request_router = request_router
        self.request_service = request_service
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_database_path = db_module.settings.database_path
        self.original_iterations = security.settings.password_pbkdf2_iterations
        self.original_prepare = request_router.prepare_face_upload
        self.original_save_request_images = request_service.save_request_images
        self.original_prepare_requested_images = request_service._prepare_requested_images
        self.original_save_face_image = request_service.save_face_image
        self.original_delete_request_images = request_service.delete_request_images
        self.original_delete_face_image_files = request_service.delete_face_image_files
        db_module.settings.database_path = str(Path(self.temp_dir.name) / "face_registration_requests.db")
        security.settings.password_pbkdf2_iterations = 1_000
        db_module.settings.default_admin_username = "admin"
        db_module.settings.default_admin_password = "admin123"
        db_module.init_db()

        prepare_counter = itertools.count(1)
        official_counter = itertools.count(1)

        def fake_prepare(data, _label):
            index = next(prepare_counter)
            return {"data": data, "embedding": np.array([index, index + 0.1], dtype=np.float32), "bbox": [1, 1, 100, 100], "quality": {"ok": True}}

        def fake_save_request_images(prepared_images):
            return "test-request", {position: f"face_requests/test-request/{position}.jpg" for position in request_service.FACE_REQUEST_POSITIONS}

        def fake_prepare_requested_images(_item):
            return [
                {"data": b"official-image", "embedding": np.array([index, index + 0.2], dtype=np.float32)}
                for index in range(1, 6)
            ]

        def fake_save_face_image(student, _data):
            return f"faces/{student['student_code']}_{next(official_counter)}.jpg"

        request_router.prepare_face_upload = fake_prepare
        request_service.save_request_images = fake_save_request_images
        request_service._prepare_requested_images = fake_prepare_requested_images
        request_service.save_face_image = fake_save_face_image
        request_service.delete_request_images = lambda _paths: None
        request_service.delete_face_image_files = lambda _paths: None

        self.admin = self.login_client("admin", "admin123")
        self.student_id = self.create_student("FACEREQ01", "Face Request Student")
        self.create_user("face-request-student", "student123", "student", self.student_id)
        self.create_user("face-request-manager", "manager123", "lab_manager")
        self.student = self.login_client("face-request-student", "student123")
        self.manager = self.login_client("face-request-manager", "manager123")

    def tearDown(self):
        if hasattr(self, "request_router"):
            self.request_router.prepare_face_upload = self.original_prepare
            self.request_service.save_request_images = self.original_save_request_images
            self.request_service._prepare_requested_images = self.original_prepare_requested_images
            self.request_service.save_face_image = self.original_save_face_image
            self.request_service.delete_request_images = self.original_delete_request_images
            self.request_service.delete_face_image_files = self.original_delete_face_image_files
        if hasattr(self, "db_module"):
            self.db_module.settings.database_path = self.original_database_path
            self.security.settings.password_pbkdf2_iterations = self.original_iterations
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

    def seed_official_faces(self, count):
        with self.db_module.get_db() as db:
            for index in range(count):
                db.execute(
                    "INSERT INTO student_faces(student_id, image_path, embedding, created_at) VALUES (?, ?, ?, ?)",
                    (self.student_id, f"faces/seed_{index}.jpg", "unused", f"2026-01-{index + 1:02d}T08:00:00"),
                )

    def submit_request(self):
        jpeg = b"\xff\xd8\xff\xe0" + b"face-request-test"
        response = self.student.post(
            "/api/student/face-registration/request",
            files=[("files", (f"face-{index}.jpg", jpeg, "image/jpeg")) for index in range(5)],
            data={"note": "Em gui yeu cau dang ky FaceID."},
            headers=self.csrf_headers(self.student),
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["item"]

    def approve_request(self, item):
        response = self.manager.patch(
            f"/api/face-registration-requests/{item['id']}/approve",
            headers=self.csrf_headers(self.manager),
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["item"]

    def official_face_count(self):
        with self.db_module.get_db() as db:
            return db.execute("SELECT COUNT(*) c FROM student_faces WHERE student_id=?", (self.student_id,)).fetchone()["c"]

    def test_student_submits_pending_request_and_manager_approves_it(self):
        item = self.submit_request()
        self.assertEqual(item["status"], "pending")
        self.assertEqual(item["request_type"], "initial")
        self.assertNotIn("front_image_path", item)

        jpeg = b"\xff\xd8\xff\xe0" + b"face-request-test"
        duplicate = self.student.post(
            "/api/student/face-registration/request",
            files=[("files", (f"face-{index}.jpg", jpeg, "image/jpeg")) for index in range(5)],
            headers=self.csrf_headers(self.student),
        )
        self.assertEqual(duplicate.status_code, 409, duplicate.text)

        listing = self.manager.get("/api/face-registration-requests?status=pending")
        self.assertEqual(listing.status_code, 200, listing.text)
        self.assertEqual(listing.json()["count"], 1)

        approved = self.approve_request(item)
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["approval_summary"]["removed_face_count"], 0)

        status = self.student.get("/api/student/face-registration")
        self.assertEqual(status.status_code, 200, status.text)
        self.assertEqual(status.json()["official_face_count"], 5)

    def test_update_from_eight_faces_replaces_three_oldest_faces(self):
        self.seed_official_faces(8)
        item = self.submit_request()
        self.assertEqual(item["request_type"], "update")
        self.assertEqual(item["face_count_at_submit"], 8)
        self.assertEqual(item["planned_remove_count"], 3)

        approved = self.approve_request(item)
        self.assertEqual(approved["approval_summary"], {
            "face_count_before": 8,
            "removed_face_count": 3,
            "face_count_after": 10,
        })
        self.assertEqual(self.official_face_count(), 10)
        with self.db_module.get_db() as db:
            old_ids = [row["id"] for row in db.execute("SELECT id FROM student_faces WHERE student_id=? ORDER BY id", (self.student_id,)).fetchall()]
        self.assertNotIn(1, old_ids)
        self.assertNotIn(2, old_ids)
        self.assertNotIn(3, old_ids)

    def test_update_from_ten_faces_replaces_five_oldest_faces(self):
        self.seed_official_faces(10)
        item = self.submit_request()
        self.assertEqual(item["planned_remove_count"], 5)

        approved = self.approve_request(item)
        self.assertEqual(approved["approval_summary"]["removed_face_count"], 5)
        self.assertEqual(self.official_face_count(), 10)

    def test_update_from_four_faces_adds_without_removing_old_faces(self):
        self.seed_official_faces(4)
        item = self.submit_request()
        self.assertEqual(item["planned_remove_count"], 0)

        approved = self.approve_request(item)
        self.assertEqual(approved["approval_summary"], {
            "face_count_before": 4,
            "removed_face_count": 0,
            "face_count_after": 9,
        })
        self.assertEqual(self.official_face_count(), 9)


if __name__ == "__main__":
    unittest.main()

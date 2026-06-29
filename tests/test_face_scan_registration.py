import itertools
import tempfile
import unittest
from pathlib import Path


class FaceScanRegistrationTests(unittest.TestCase):
    def setUp(self):
        try:
            import numpy as np
            from fastapi.testclient import TestClient
            from app import db as db_module
            from app.core import security
            from app.main import app
            import app.routers.student_faces as students_router
        except ModuleNotFoundError as exc:
            self.skipTest(f"{exc.name} is not installed in this test environment.")

        self.np = np
        self.TestClient = TestClient
        self.db_module = db_module
        self.security = security
        self.app = app
        self.students_router = students_router
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_database_path = db_module.settings.database_path
        self.original_iterations = security.settings.password_pbkdf2_iterations
        self.original_default_admin_username = db_module.settings.default_admin_username
        self.original_default_admin_password = db_module.settings.default_admin_password
        self.original_prepare_face_upload = students_router._prepare_face_upload
        self.original_save_face_image = students_router._save_face_image
        self.original_delete_face_image_files = students_router._delete_face_image_files

        db_module.settings.database_path = str(Path(self.temp_dir.name) / "face_scan_registration.db")
        db_module.settings.password_pbkdf2_iterations = 1_000
        db_module.settings.default_admin_username = "admin"
        db_module.settings.default_admin_password = "admin123"
        db_module.init_db()

        prepare_counter = itertools.count(1)
        save_counter = itertools.count(1)

        def fake_prepare_face_upload(data, _label):
            index = next(prepare_counter)
            return {
                "data": data,
                "embedding": np.array([index, index + 0.5], dtype=np.float32),
                "bbox": [10, 20, 110, 160],
                "quality": {"ok": True, "reason": "ok"},
            }

        def fake_save_face_image(student, _data):
            return f"faces/{student['student_code']}_scan_{next(save_counter)}.jpg"

        students_router._prepare_face_upload = fake_prepare_face_upload
        students_router._save_face_image = fake_save_face_image
        students_router._delete_face_image_files = lambda _paths: None

    def tearDown(self):
        if hasattr(self, "students_router"):
            self.students_router._prepare_face_upload = self.original_prepare_face_upload
            self.students_router._save_face_image = self.original_save_face_image
            self.students_router._delete_face_image_files = self.original_delete_face_image_files
        if hasattr(self, "db_module"):
            self.db_module.settings.database_path = self.original_database_path
            self.security.settings.password_pbkdf2_iterations = self.original_iterations
            self.db_module.settings.default_admin_username = self.original_default_admin_username
            self.db_module.settings.default_admin_password = self.original_default_admin_password
        if hasattr(self, "temp_dir"):
            self.temp_dir.cleanup()

    def client(self):
        return self.TestClient(self.app, base_url="http://127.0.0.1")

    def csrf_headers(self, client):
        return {"X-CSRF-Token": client.cookies.get("csrf_token", "")}

    def login(self, client):
        response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        self.assertEqual(response.status_code, 200, response.text)

    def create_student(self, client):
        response = client.post(
            "/api/students",
            json={
                "student_code": "SVSCAN01",
                "full_name": "Scan Test",
                "class_name": "LAB",
                "status": "active",
            },
            headers=self.csrf_headers(client),
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["id"]

    def face_count(self, student_id):
        with self.db_module.get_db() as db:
            return db.execute(
                "SELECT COUNT(*) c FROM student_faces WHERE student_id=?",
                (student_id,),
            ).fetchone()["c"]

    def test_scan_registers_five_faces_on_first_submit(self):
        client = self.client()
        self.login(client)
        student_id = self.create_student(client)

        jpeg_bytes = b"\xff\xd8\xff\xe0" + b"face-scan-test"
        files = [
            ("files", (f"scan_{index}.jpg", jpeg_bytes, "image/jpeg"))
            for index in range(5)
        ]
        response = client.post(
            f"/api/students/{student_id}/faces/scan",
            files=files,
            headers=self.csrf_headers(client),
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["face_count"], 5)
        self.assertEqual(self.face_count(student_id), 5)


if __name__ == "__main__":
    unittest.main()

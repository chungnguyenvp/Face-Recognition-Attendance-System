import sqlite3
import tempfile
import unittest
from pathlib import Path

from app import db as db_module
from app.repositories import face_registration_request_repository as repository


class FaceRegistrationRequestRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.original_database_path = db_module.settings.database_path
        self.temp_dir = tempfile.TemporaryDirectory()
        db_module.settings.database_path = str(Path(self.temp_dir.name) / "face_requests.db")
        db_module.init_db()
        with db_module.get_db() as db:
            self.student_id = db.execute(
                "INSERT INTO students(student_code, full_name, created_at) VALUES (?, ?, ?)",
                ("REQ001", "Request Student", "2026-06-23T08:00:00"),
            ).lastrowid

    def tearDown(self):
        db_module.settings.database_path = self.original_database_path
        self.temp_dir.cleanup()

    def test_create_update_request_records_capacity_snapshot_and_enforces_one_pending(self):
        image_paths = {
            "front": "face_requests/key/front.jpg",
            "left": "face_requests/key/left.jpg",
            "right": "face_requests/key/right.jpg",
            "up": "face_requests/key/up.jpg",
            "down": "face_requests/key/down.jpg",
        }
        with db_module.get_db() as db:
            request_id = repository.create_request(
                db,
                self.student_id,
                "update",
                8,
                3,
                "key",
                image_paths,
                "Cap nhat anh FaceID.",
                "2026-06-23T08:05:00",
            )
            row = repository.get_request_by_id(db, request_id)
            self.assertEqual(row["request_type"], "update")
            self.assertEqual(row["face_count_at_submit"], 8)
            self.assertEqual(row["planned_remove_count"], 3)
            with self.assertRaises(sqlite3.IntegrityError):
                repository.create_request(
                    db,
                    self.student_id,
                    "update",
                    8,
                    3,
                    "key-2",
                    image_paths,
                    None,
                    "2026-06-23T08:06:00",
                )


if __name__ == "__main__":
    unittest.main()

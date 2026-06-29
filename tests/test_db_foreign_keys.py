import sqlite3
import tempfile
import unittest
from pathlib import Path

from app import db as db_module


class DatabaseForeignKeyTests(unittest.TestCase):
    def setUp(self):
        self.original_database_path = db_module.settings.database_path
        self.temp_dir = tempfile.TemporaryDirectory()
        db_module.settings.database_path = str(Path(self.temp_dir.name) / "face_lab_test.db")
        db_module.init_db()

    def tearDown(self):
        db_module.settings.database_path = self.original_database_path
        self.temp_dir.cleanup()

    def test_get_db_enables_foreign_key_enforcement(self):
        with db_module.get_db() as db:
            enabled = db.execute("PRAGMA foreign_keys").fetchone()[0]

        self.assertEqual(enabled, 1)

    def test_get_db_sets_busy_timeout(self):
        with db_module.get_db() as db:
            timeout = db.execute("PRAGMA busy_timeout").fetchone()[0]

        self.assertEqual(timeout, 5000)

    def test_init_db_enables_wal_journal_mode(self):
        with db_module.get_db() as db:
            journal_mode = db.execute("PRAGMA journal_mode").fetchone()[0]

        self.assertEqual(journal_mode.lower(), "wal")

    def test_invalid_student_face_reference_is_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with db_module.get_db() as db:
                db.execute(
                    """
                    INSERT INTO student_faces(student_id, image_path, embedding, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (999_999, "faces/missing.jpg", "embedding", "2026-06-11T00:00:00"),
                )

    def test_face_registration_request_schema_and_pending_index_exist(self):
        with db_module.get_db() as db:
            table = db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='face_registration_requests'"
            ).fetchone()
            indexes = db.execute("PRAGMA index_list(face_registration_requests)").fetchall()
            columns = db.execute("PRAGMA table_info(face_registration_requests)").fetchall()

        self.assertIsNotNone(table)
        self.assertIn("idx_face_registration_requests_one_pending", {row["name"] for row in indexes})
        self.assertTrue(
            {"request_type", "face_count_at_submit", "planned_remove_count"}.issubset(
                {row["name"] for row in columns}
            )
        )


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from app import db as db_module
from app.services import attendance_transition_service


class AttendanceTransitionServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_database_path = db_module.settings.database_path
        db_module.settings.database_path = str(Path(self.temp_dir.name) / "attendance_transition.db")
        db_module.init_db()

    def tearDown(self):
        db_module.settings.database_path = self.original_database_path
        self.temp_dir.cleanup()

    def create_student(self):
        with db_module.get_db() as db:
            cur = db.execute(
                """
                INSERT INTO students(student_code, full_name, class_name, status, created_at)
                VALUES ('SV001', 'Nguyen Van A', 'CNTT', 'active', '2025-01-01T00:00:00')
                """
            )
            return cur.lastrowid

    def create_check_in(self, student_id: int, created_at: str):
        with db_module.get_db() as db:
            db.execute(
                """
                INSERT INTO access_logs(student_id, student_code, full_name, action, result, created_at)
                VALUES (?, 'SV001', 'Nguyen Van A', 'check_in', 'success', ?)
                """,
                (student_id, created_at),
            )

    def test_rejects_check_out_before_check_in(self):
        student_id = self.create_student()

        allowed, note = attendance_transition_service.validate_attendance_transition(student_id, "check_out")

        self.assertFalse(allowed)
        self.assertIn("chưa check-in", note)

    def test_rejects_duplicate_check_in_on_same_day(self):
        student_id = self.create_student()
        self.create_check_in(student_id, datetime.now().replace(hour=8, minute=0, second=0, microsecond=0).isoformat())

        allowed, note = attendance_transition_service.validate_attendance_transition(student_id, "check_in")

        self.assertFalse(allowed)
        self.assertIn("chưa check-out", note)

    def test_allows_check_in_after_stale_check_in_is_finalized(self):
        student_id = self.create_student()
        stale_date = (datetime.now().date() - timedelta(days=1)).isoformat()
        self.create_check_in(student_id, f"{stale_date}T08:00:00")

        allowed, note = attendance_transition_service.validate_attendance_transition(student_id, "check_in")

        self.assertTrue(allowed)
        self.assertIsNone(note)
        self.assertEqual(attendance_transition_service.current_presence_state(student_id), "outside")


if __name__ == "__main__":
    unittest.main()

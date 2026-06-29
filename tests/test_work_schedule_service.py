import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from app import db as db_module
from app.repositories import work_schedule_repository
from app.services import attendance_service, work_schedule_service


class WorkScheduleServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_database_path = db_module.settings.database_path
        db_module.settings.database_path = str(Path(self.temp_dir.name) / "work_schedule.db")
        db_module.init_db()
        with db_module.get_db() as db:
            self.student_id = db.execute(
                """
                INSERT INTO students(student_code, full_name, class_name, status, created_at)
                VALUES ('SV001', 'Nguyen Van A', 'CNTT', 'active', '2025-01-01T00:00:00')
                """
            ).lastrowid
            work_schedule_repository.upsert_schedule(db, {
                "effective_from": "1970-01-01",
                "monday_enabled": True, "tuesday_enabled": True, "wednesday_enabled": True,
                "thursday_enabled": True, "friday_enabled": True, "saturday_enabled": False,
                "sunday_enabled": False, "start_time": "08:00", "end_time": "17:00",
                "late_allowed_minutes": 5, "early_leave_allowed_minutes": 10,
                "checkout_cutoff_time": "20:00", "updated_at": "2025-01-01T00:00:00",
            })

    def tearDown(self):
        db_module.settings.database_path = self.original_database_path
        self.temp_dir.cleanup()

    def test_exception_has_priority_over_weekly_schedule(self):
        with db_module.get_db() as db:
            work_schedule_repository.upsert_exception(db, None, {
                "exception_date": "2025-01-02", "exception_type": "off", "holiday_name": "Nghỉ đặc biệt",
                "note": "Nghỉ toàn lab", "created_at": "2025-01-01T00:00:00", "updated_at": "2025-01-01T00:00:00",
            })
            holiday = work_schedule_service.get_day_policy(db, "2025-01-02")
            saturday = work_schedule_service.get_day_policy(db, "2025-01-04")
            friday = work_schedule_service.get_day_policy(db, "2025-01-03")

        self.assertFalse(holiday["is_working_day"])
        self.assertEqual(holiday["status"], "special_holiday")
        self.assertFalse(saturday["is_working_day"])
        self.assertEqual(saturday["status"], "weekend_off")
        self.assertTrue(friday["is_working_day"])

    def test_day_off_does_not_create_absence_but_keeps_checkin_audit(self):
        attendance_service.ensure_attendance_records("2025-01-04")
        with db_module.get_db() as db:
            self.assertIsNone(db.execute("SELECT * FROM attendance_records WHERE student_id=?", (self.student_id,)).fetchone())
            db.execute(
                """
                INSERT INTO access_logs(student_id, student_code, full_name, action, result, created_at)
                VALUES (?, 'SV001', 'Nguyen Van A', 'check_in', 'success', '2025-01-04T09:00:00')
                """,
                (self.student_id,),
            )
            student = db.execute("SELECT id, student_code, full_name FROM students WHERE id=?", (self.student_id,)).fetchone()
            attendance_service._upsert_attendance_record(db, student, "2025-01-04")
            record = db.execute("SELECT status, late_minutes, missing_checkout FROM attendance_records WHERE student_id=?", (self.student_id,)).fetchone()

        self.assertEqual(record["status"], "off_day")
        self.assertEqual(record["late_minutes"], 0)
        self.assertEqual(record["missing_checkout"], 0)
        self.assertEqual(attendance_service.mark_missing_checkouts(datetime(2025, 1, 4, 21, 0), "20:00"), 0)

    def test_leave_count_only_includes_working_days(self):
        with db_module.get_db() as db:
            days = work_schedule_service.working_days_between(db, "2025-01-03", "2025-01-05")
        self.assertEqual([item.isoformat() for item in days], ["2025-01-03"])


if __name__ == "__main__":
    unittest.main()

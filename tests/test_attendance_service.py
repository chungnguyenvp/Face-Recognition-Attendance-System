import tempfile
import unittest
from datetime import datetime, time, timedelta
from pathlib import Path

from app import db as db_module
from app.services import attendance_service


class AttendanceServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_database_path = db_module.settings.database_path
        db_module.settings.database_path = str(Path(self.temp_dir.name) / "attendance_service.db")
        db_module.init_db()

    def tearDown(self):
        db_module.settings.database_path = self.original_database_path
        self.temp_dir.cleanup()

    def create_student(self, student_code="SV001", full_name="Nguyen Van A"):
        with db_module.get_db() as db:
            cur = db.execute(
                """
                INSERT INTO students(student_code, full_name, class_name, status, created_at)
                VALUES (?, ?, 'CNTT', 'active', ?)
                """,
                (student_code, full_name, "2025-01-01T00:00:00"),
            )
            return cur.lastrowid

    def create_check_in(self, student_id, student_code="SV001", full_name="Nguyen Van A", created_at="2025-01-02T08:00:00"):
        self.create_access_log(student_id, "check_in", student_code, full_name, created_at)

    def create_access_log(self, student_id, action, student_code="SV001", full_name="Nguyen Van A", created_at="2025-01-02T08:00:00"):
        with db_module.get_db() as db:
            db.execute(
                """
                INSERT INTO access_logs(student_id, student_code, full_name, action, result, confidence, note, evidence_image_path, created_at)
                VALUES (?, ?, ?, ?, 'success', NULL, NULL, NULL, ?)
                """,
                (student_id, student_code, full_name, action, created_at),
            )

    def create_missing_checkout_record(self, student_id, attendance_date="2025-01-02"):
        with db_module.get_db() as db:
            cur = db.execute(
                """
                INSERT INTO attendance_records(
                    student_id, student_code, full_name, attendance_date,
                    status, missing_checkout, created_at, updated_at
                )
                VALUES (?, 'SV001', 'Nguyen Van A', ?, 'missing_checkout', 1, ?, ?)
                """,
                (student_id, attendance_date, f"{attendance_date}T18:00:00", f"{attendance_date}T18:00:00"),
            )
            return cur.lastrowid

    def test_attendance_status_calculates_late_and_early_leave(self):
        status, late_minutes, early_leave_minutes, note = attendance_service._attendance_status(
            "2025-01-02",
            "2025-01-02T08:10:00",
            "2025-01-02T16:40:00",
            False,
            {
                "work_start_time": time(8, 0),
                "work_end_time": time(17, 0),
                "late_grace_minutes": 5,
                "early_leave_grace_minutes": 10,
            },
            now=datetime(2025, 1, 2, 18, 0),
            last_action="check_out",
        )

        self.assertEqual(status, "late_and_early_leave")
        self.assertEqual(late_minutes, 5)
        self.assertEqual(early_leave_minutes, 10)
        self.assertIsNone(note)

    def test_mark_missing_checkouts_auto_closes_once_and_keeps_record_finalized(self):
        student_id = self.create_student()
        self.create_check_in(student_id)
        now = datetime(2025, 1, 2, 21, 0)

        self.assertEqual(attendance_service.mark_missing_checkouts(now, "20:00"), 1)
        self.assertEqual(attendance_service.mark_missing_checkouts(now, "20:00"), 0)

        with db_module.get_db() as db:
            record = db.execute("SELECT * FROM attendance_records WHERE student_id=?", (student_id,)).fetchone()
            check_out_count = db.execute(
                "SELECT COUNT(*) AS count FROM access_logs WHERE student_id=? AND action='check_out'",
                (student_id,),
            ).fetchone()["count"]
            alert_count = db.execute("SELECT COUNT(*) AS count FROM alerts").fetchone()["count"]

        self.assertEqual(record["status"], "present_on_time")
        self.assertEqual(record["missing_checkout"], 0)
        self.assertEqual(record["missing_checkout_resolution"], "auto_work_end")
        self.assertEqual(check_out_count, 1)
        self.assertEqual(alert_count, 1)

    def test_manual_missing_checkout_resolution_adds_check_out_and_updates_record(self):
        student_id = self.create_student()
        self.create_check_in(student_id)
        record_id = self.create_missing_checkout_record(student_id)

        record = attendance_service.resolve_missing_checkout_record(
            record_id,
            "manual_time",
            "Da xac minh gio ra.",
            "17:00",
        )

        self.assertIsNotNone(record)
        self.assertEqual(record["status"], "present_on_time")
        self.assertEqual(record["total_minutes"], 540)
        self.assertEqual(record["missing_checkout"], 0)
        self.assertEqual(record["missing_checkout_resolution"], "manual_time")
        self.assertEqual(record["resolution_reason"], "Da xac minh gio ra.")
        self.assertEqual(record["resolution_checkout_at"], "2025-01-02T17:00:00")

        with db_module.get_db() as db:
            check_out = db.execute(
                "SELECT action, result, created_at FROM access_logs WHERE student_id=? AND action='check_out'",
                (student_id,),
            ).fetchone()

        self.assertEqual(dict(check_out), {
            "action": "check_out",
            "result": "success",
            "created_at": "2025-01-02T17:00:00",
        })

    def test_work_end_missing_checkout_resolution_uses_configured_end_time(self):
        student_id = self.create_student()
        self.create_check_in(student_id)
        record_id = self.create_missing_checkout_record(student_id)

        record = attendance_service.resolve_missing_checkout_record(
            record_id,
            "work_end",
            "Chot theo gio ket thuc ca.",
        )

        self.assertIsNotNone(record)
        self.assertEqual(record["status"], "present_on_time")
        self.assertEqual(record["total_minutes"], 540)
        self.assertEqual(record["missing_checkout_resolution"], "work_end")
        self.assertEqual(record["resolution_checkout_at"], "2025-01-02T17:00:00")

    def test_manual_missing_checkout_resolution_rejects_invalid_time(self):
        student_id = self.create_student()
        self.create_check_in(student_id)
        record_id = self.create_missing_checkout_record(student_id)

        with self.assertRaises(ValueError):
            attendance_service.resolve_missing_checkout_record(
                record_id,
                "manual_time",
                "Sai gio.",
                "25:99",
            )

    def test_keep_zero_missing_checkout_resolution_keeps_zero_minutes(self):
        student_id = self.create_student()
        self.create_check_in(student_id)
        record_id = self.create_missing_checkout_record(student_id)

        record = attendance_service.resolve_missing_checkout_record(
            record_id,
            "keep_zero",
            "Khong co du lieu gio ra.",
        )

        self.assertIsNotNone(record)
        self.assertEqual(record["status"], "missing_checkout")
        self.assertEqual(record["total_minutes"], 0)
        self.assertEqual(record["missing_checkout"], 1)
        self.assertEqual(record["missing_checkout_resolution"], "keep_zero")
        self.assertEqual(record["force_zero_minutes"], 1)

        with db_module.get_db() as db:
            check_out_count = db.execute(
                "SELECT COUNT(*) AS count FROM access_logs WHERE student_id=? AND action='check_out'",
                (student_id,),
            ).fetchone()["count"]

        self.assertEqual(check_out_count, 0)

    def test_attendance_context_summarizes_multiple_sessions_and_outside_time(self):
        student_id = self.create_student()
        self.create_check_in(student_id, created_at="2025-01-02T08:00:00")
        self.create_access_log(student_id, "check_out", created_at="2025-01-02T12:00:00")
        self.create_check_in(student_id, created_at="2025-01-02T13:00:00")
        self.create_access_log(student_id, "check_out", created_at="2025-01-02T17:00:00")

        with db_module.get_db() as db:
            context = attendance_service.attendance_record_context(db, student_id, "2025-01-02")

        self.assertEqual(context["total_minutes"], 480)
        self.assertEqual(context["outside_count"], 1)
        self.assertEqual(context["outside_minutes"], 60)
        self.assertEqual(context["last_action"], "check_out")
        self.assertEqual(context["presence_status"], "out_of_lab")

    def test_upsert_uses_student_specific_work_schedule(self):
        student_id = self.create_student()
        self.create_check_in(student_id, created_at="2025-01-02T08:10:00")
        self.create_access_log(student_id, "check_out", created_at="2025-01-02T16:45:00")

        with db_module.get_db() as db:
            db.execute(
                """
                INSERT INTO student_attendance_settings(student_id, work_start_time, work_end_time, updated_at)
                VALUES (?, '07:30', '16:45', '2025-01-01T00:00:00')
                """,
                (student_id,),
            )
            db.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('late_grace_minutes', '5')")
            db.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('early_leave_grace_minutes', '10')")
            student = db.execute(
                "SELECT id, student_code, full_name FROM students WHERE id=?",
                (student_id,),
            ).fetchone()
            attendance_service._upsert_attendance_record(db, student, "2025-01-02")
            record = db.execute(
                "SELECT status, late_minutes, early_leave_minutes, total_minutes FROM attendance_records WHERE student_id=?",
                (student_id,),
            ).fetchone()

        self.assertEqual(record["status"], "late")
        self.assertEqual(record["late_minutes"], 35)
        self.assertEqual(record["early_leave_minutes"], 0)
        self.assertEqual(record["total_minutes"], 515)

    def test_stale_check_in_is_finalized_before_a_new_day(self):
        student_id = self.create_student()
        stale_date = (datetime.now().date() - timedelta(days=1)).isoformat()
        self.create_check_in(student_id, created_at=f"{stale_date}T08:00:00")

        self.assertTrue(attendance_service.mark_stale_checkin_missing_checkout(student_id))

        with db_module.get_db() as db:
            record = db.execute(
                "SELECT missing_checkout_resolution, missing_checkout FROM attendance_records WHERE student_id=?",
                (student_id,),
            ).fetchone()
            check_out_count = db.execute(
                "SELECT COUNT(*) AS count FROM access_logs WHERE student_id=? AND action='check_out'",
                (student_id,),
            ).fetchone()["count"]

        self.assertEqual(record["missing_checkout_resolution"], "auto_work_end")
        self.assertEqual(record["missing_checkout"], 0)
        self.assertEqual(check_out_count, 1)

    def test_recalculate_student_record_is_idempotent(self):
        student_id = self.create_student()
        attendance_date = (datetime.now().date() - timedelta(days=1)).isoformat()
        self.create_check_in(student_id, created_at=f"{attendance_date}T08:00:00")
        self.create_access_log(student_id, "check_out", created_at=f"{attendance_date}T17:00:00")

        self.assertTrue(attendance_service.recalculate_student_attendance_record(student_id, attendance_date))
        self.assertTrue(attendance_service.recalculate_student_attendance_record(student_id, attendance_date))

        with db_module.get_db() as db:
            records = db.execute(
                "SELECT status, total_minutes FROM attendance_records WHERE student_id=? AND attendance_date=?",
                (student_id, attendance_date),
            ).fetchall()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["status"], "present_on_time")
        self.assertEqual(records[0]["total_minutes"], 540)


if __name__ == "__main__":
    unittest.main()

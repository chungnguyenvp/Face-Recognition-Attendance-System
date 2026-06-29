import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from app import db as db_module
from app.repositories import attendance_repository, leave_repository
from app.schemas.leave import LeaveRequestCreate
from app.services import leave_service


class LeaveServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_database_path = db_module.settings.database_path
        db_module.settings.database_path = str(Path(self.temp_dir.name) / "leave_service.db")
        db_module.init_db()
        now = datetime.now().isoformat(timespec="seconds")
        with db_module.get_db() as db:
            db.execute(
                "INSERT INTO students(student_code, full_name, status, created_at) VALUES (?, ?, 'active', ?)",
                ("SVLEAVE", "Leave Student", now),
            )
            self.student_id = db.execute("SELECT id FROM students WHERE student_code='SVLEAVE'").fetchone()["id"]
            db.execute(
                "INSERT INTO users(username, password_hash, role, student_id, status, created_at) VALUES (?, ?, 'student', ?, 'active', ?)",
                ("leave-student", "test", self.student_id, now),
            )
            db.execute(
                "INSERT INTO users(username, password_hash, role, status, created_at) VALUES (?, ?, 'lab_manager', 'active', ?)",
                ("leave-manager", "test", now),
            )
            self.student_user_id = db.execute("SELECT id FROM users WHERE username='leave-student'").fetchone()["id"]
            self.manager_user_id = db.execute("SELECT id FROM users WHERE username='leave-manager'").fetchone()["id"]
        self.student_actor = {"id": self.student_user_id, "username": "leave-student", "role": "student", "student_id": self.student_id}
        self.manager_actor = {"id": self.manager_user_id, "username": "leave-manager", "role": "lab_manager"}
        self.start = (date.today() + timedelta(days=2)).isoformat()
        self.end = (date.today() + timedelta(days=3)).isoformat()

    def tearDown(self):
        db_module.settings.database_path = self.original_database_path
        self.temp_dir.cleanup()

    def create_payload(self):
        return LeaveRequestCreate(
            leave_type="sick",
            start_date=self.start,
            end_date=self.end,
            reason="Can nghi de dieu tri benh.",
        )

    def test_create_approve_and_revoke_recalculates_attendance(self):
        with db_module.get_db() as db:
            item = leave_service.create_leave_request(db, self.student_actor, self.create_payload())
            record = attendance_repository.get_attendance_record_by_student_date(db, self.student_id, self.start)
            self.assertEqual(item["status"], "pending")
            self.assertEqual(record["status"], "leave_pending")

        with db_module.get_db() as db:
            item = leave_service.review_leave_request(db, self.manager_actor, item["id"], "approved", None)
            record = attendance_repository.get_attendance_record_by_student_date(db, self.student_id, self.start)
            self.assertEqual(item["status"], "approved")
            self.assertEqual(record["status"], "leave_approved")

        with db_module.get_db() as db:
            admin_actor = {**self.manager_actor, "role": "admin"}
            item = leave_service.revoke_leave_request(db, admin_actor, item["id"], "Duyet nham.")
            record = attendance_repository.get_attendance_record_by_student_date(db, self.student_id, self.start)
            self.assertEqual(item["status"], "revoked")
            self.assertEqual(record["status"], "pending")

    def test_rejects_overlapping_and_past_requests(self):
        with db_module.get_db() as db:
            leave_service.create_leave_request(db, self.student_actor, self.create_payload())

        with db_module.get_db() as db:
            overlap = LeaveRequestCreate(
                leave_type="personal",
                start_date=self.start,
                end_date=(date.today() + timedelta(days=4)).isoformat(),
                reason="Can xu ly viec gia dinh.",
            )
            with self.assertRaises(ValueError):
                leave_service.create_leave_request(db, self.student_actor, overlap)
            self.assertTrue(leave_repository.has_overlapping_leave_request(db, self.student_id, self.start, self.end))

        with db_module.get_db() as db:
            past = LeaveRequestCreate(
                leave_type="sick",
                start_date=(date.today() - timedelta(days=1)).isoformat(),
                end_date=(date.today() - timedelta(days=1)).isoformat(),
                reason="Xin nghi sau ngay da qua.",
            )
            with self.assertRaises(ValueError):
                leave_service.create_leave_request(db, self.student_actor, past)


if __name__ == "__main__":
    unittest.main()

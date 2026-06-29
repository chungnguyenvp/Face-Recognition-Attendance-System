import tempfile
import unittest
from pathlib import Path

from app import db as db_module
from app.services import access_event_service


class AccessEventServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_database_path = db_module.settings.database_path
        db_module.settings.database_path = str(Path(self.temp_dir.name) / "access_event_service.db")
        db_module.init_db()

    def tearDown(self):
        db_module.settings.database_path = self.original_database_path
        self.temp_dir.cleanup()

    def test_success_log_writes_event_and_invokes_callback(self):
        with db_module.get_db() as db:
            db.execute(
                """
                INSERT INTO students(id, student_code, full_name, class_name, status, created_at)
                VALUES (7, 'SV007', 'Nguyen Van A', 'CNTT', 'active', '2025-01-01T00:00:00')
                """
            )
        student = {"student_id": 7, "student_code": "SV007", "full_name": "Nguyen Van A"}
        callback_events = []

        access_event_service.log_access(
            student,
            "check_in",
            "success",
            confidence=0.9,
            note="Camera realtime",
            on_success=lambda item, action, created_at: callback_events.append((item, action, created_at)),
        )

        with db_module.get_db() as db:
            row = db.execute("SELECT * FROM access_logs").fetchone()

        self.assertEqual(row["student_id"], 7)
        self.assertEqual(row["student_code"], "SV007")
        self.assertEqual(row["action"], "check_in")
        self.assertEqual(row["result"], "success")
        self.assertEqual(len(callback_events), 1)
        self.assertEqual(callback_events[0][0], student)
        self.assertEqual(callback_events[0][1], "check_in")

    def test_non_success_log_does_not_invoke_callback_and_alert_is_created(self):
        callbacks = []
        access_event_service.log_access(
            None,
            "check_in",
            "warning",
            on_success=lambda *args: callbacks.append(args),
        )
        access_event_service.create_alert("unknown_face", "Unknown face", event_date="2025-01-02")

        with db_module.get_db() as db:
            log = db.execute("SELECT student_code, result FROM access_logs").fetchone()
            alert = db.execute("SELECT type, message, event_date FROM alerts").fetchone()

        self.assertEqual(callbacks, [])
        self.assertEqual(dict(log), {"student_code": "Unknown", "result": "warning"})
        self.assertEqual(dict(alert), {"type": "unknown_face", "message": "Unknown face", "event_date": "2025-01-02"})


if __name__ == "__main__":
    unittest.main()

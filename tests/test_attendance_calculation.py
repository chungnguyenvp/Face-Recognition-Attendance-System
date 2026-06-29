import unittest

from app.services.attendance_calculation import summarize_day_logs


class AttendanceCalculationTests(unittest.TestCase):
    def test_summarize_day_logs_calculates_sessions_and_outside_periods(self):
        summary = summarize_day_logs(
            [
                {"action": "check_in", "created_at": "2025-01-02T08:00:00", "note": None},
                {"action": "check_out", "created_at": "2025-01-02T12:00:00", "note": None},
                {"action": "check_in", "created_at": "2025-01-02T13:00:00", "note": None},
                {"action": "check_out", "created_at": "2025-01-02T17:00:00", "note": "Done"},
            ]
        )

        self.assertEqual(summary["total_minutes"], 480)
        self.assertEqual(summary["outside_count"], 1)
        self.assertEqual(summary["outside_minutes"], 60)
        self.assertEqual(summary["presence_status"], "out_of_lab")
        self.assertEqual(summary["last_log_at"], "2025-01-02T17:00:00")
        self.assertEqual(summary["logs"][-1]["note"], "Done")


if __name__ == "__main__":
    unittest.main()

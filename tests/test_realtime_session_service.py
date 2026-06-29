import unittest

from app.services import realtime_session_service
from app.services.realtime_session_service import build_session_key, session_decision


class RealtimeSessionServiceTests(unittest.TestCase):
    def setUp(self):
        realtime_session_service._presence_sessions.clear()

    @staticmethod
    def recognized_item(liveness_status="live"):
        return {
            "recognized": True,
            "student_id": 999999,
            "student_code": "TEST",
            "full_name": "Test User",
            "bbox": [0, 0, 100, 100],
            "liveness_status": liveness_status,
            "liveness": {"real_score": 0.9 if liveness_status == "live" else 0.1},
            "quality": {"ok": True},
        }

    def test_session_key_builder_remains_callable_after_decisions(self):
        item = self.recognized_item()

        expected_key = "student:999999:check_in"
        self.assertEqual(build_session_key("check_in", item), expected_key)

        for _ in range(2):
            _, current_session_key, _ = session_decision("check_in", item)
            self.assertEqual(current_session_key, expected_key)
            self.assertTrue(callable(build_session_key))

    def test_recognized_live_face_succeeds_after_six_frames(self):
        decisions = [
            session_decision("check_in", self.recognized_item())[0]
            for _ in range(6)
        ]

        self.assertEqual(decisions, [None, None, None, None, None, "success"])

    def test_recognized_fake_face_is_denied_after_ten_frames(self):
        decisions = [
            session_decision("check_in", self.recognized_item("fake"))[0]
            for _ in range(10)
        ]

        self.assertEqual(decisions[:9], [None] * 9)
        self.assertEqual(decisions[9], "denied")

    def test_recognized_face_is_denied_with_eight_fake_votes_in_ten_frames(self):
        statuses = ["fake", "fake", "fake", "live", "fake", "fake", "fake", "live", "fake", "fake"]
        decisions = [
            session_decision("check_in", self.recognized_item(status))[0]
            for status in statuses
        ]

        self.assertEqual(decisions[:9], [None] * 9)
        self.assertEqual(decisions[9], "denied")

    def test_unknown_live_face_warns_after_ten_frames(self):
        item = {
            "recognized": False,
            "student_id": None,
            "bbox": [0, 0, 100, 100],
            "liveness_status": "live",
            "liveness": {"real_score": 0.9},
            "quality": {"ok": True},
        }
        decisions = [session_decision("check_in", item.copy())[0] for _ in range(10)]

        self.assertEqual(decisions[:9], [None] * 9)
        self.assertEqual(decisions[9], "warning")

    def test_temporary_unknown_frame_keeps_active_student_session(self):
        _, student_key, _ = session_decision("check_in", self.recognized_item())
        unknown_item = {
            "recognized": False,
            "student_id": None,
            "bbox": [5, 5, 105, 105],
            "liveness_status": "fake",
            "liveness": {"real_score": 0.1},
            "quality": {"ok": True},
        }

        decision, current_key, state = session_decision("check_in", unknown_item)

        self.assertIsNone(decision)
        self.assertEqual(current_key, student_key)
        self.assertEqual(state, "pending")
        self.assertEqual(unknown_item["display_student_id"], 999999)


if __name__ == "__main__":
    unittest.main()

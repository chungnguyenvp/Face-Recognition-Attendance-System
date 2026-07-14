import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

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

    @staticmethod
    def unknown_item(bbox=None, liveness_status="live"):
        return {
            "recognized": False,
            "student_id": None,
            "bbox": bbox or [0, 0, 100, 100],
            "liveness_status": liveness_status,
            "liveness": {"real_score": 0.9 if liveness_status == "live" else 0.1},
            "quality": {"ok": True},
        }

    def test_session_key_builder_remains_callable_after_decisions(self):
        item = self.recognized_item()

        expected_key = "default:student:999999:check_in"
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
        item = self.unknown_item()
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

    def test_recognized_votes_do_not_mix_between_sources(self):
        first_round = [
            session_decision("check_in", self.recognized_item(), scope)[0]
            for _ in range(3)
            for scope in ("camera-a", "camera-b")
        ]

        self.assertEqual(first_round, [None] * 6)
        camera_a = [
            session_decision("check_in", self.recognized_item(), "camera-a")[0]
            for _ in range(3)
        ]
        camera_b = [
            session_decision("check_in", self.recognized_item(), "camera-b")[0]
            for _ in range(3)
        ]

        self.assertEqual(camera_a, [None, None, "success"])
        self.assertEqual(camera_b, [None, None, "success"])

    def test_unknown_votes_do_not_mix_between_sources(self):
        decisions = [
            session_decision("check_in", self.unknown_item(), scope)[0]
            for _ in range(5)
            for scope in ("camera-a", "camera-b")
        ]

        self.assertEqual(decisions, [None] * 10)
        camera_a = [
            session_decision("check_in", self.unknown_item(), "camera-a")[0]
            for _ in range(5)
        ]

        self.assertEqual(camera_a, [None, None, None, None, "warning"])

    def test_different_unknown_tracks_in_one_source_do_not_mix(self):
        face_a = [0, 0, 100, 100]
        face_b = [500, 500, 600, 600]
        keys = {"a": set(), "b": set()}
        decisions = []
        for _ in range(5):
            decision_a, key_a, _ = session_decision(
                "check_in", self.unknown_item(face_a), "camera-a"
            )
            decision_b, key_b, _ = session_decision(
                "check_in", self.unknown_item(face_b), "camera-a"
            )
            keys["a"].add(key_a)
            keys["b"].add(key_b)
            decisions.extend((decision_a, decision_b))

        self.assertEqual(decisions, [None] * 10)
        self.assertEqual(len(keys["a"]), 1)
        self.assertEqual(len(keys["b"]), 1)
        self.assertTrue(keys["a"].isdisjoint(keys["b"]))

    def test_cleanup_only_removes_sessions_from_requested_scope(self):
        session_decision("check_in", self.recognized_item(), "camera-a")
        session_decision("check_in", self.recognized_item(), "camera-b")
        with realtime_session_service._presence_store.lock:
            for session in realtime_session_service._presence_sessions.values():
                session["last_seen"] = 0

        realtime_session_service.cleanup_presence_sessions(set(), "camera-a")

        remaining_scopes = {
            session["scope_id"]
            for session in realtime_session_service._presence_sessions.values()
        }
        self.assertEqual(remaining_scopes, {"camera-b"})

    def test_parallel_votes_are_serialized_and_finalize_once(self):
        def vote(_index):
            return session_decision(
                "check_in", self.recognized_item(), "camera-parallel"
            )[0]

        with ThreadPoolExecutor(max_workers=8) as executor:
            decisions = list(executor.map(vote, range(32)))

        self.assertEqual(decisions.count("success"), 1)
        self.assertNotIn("denied", decisions)

    def test_cleanup_and_updates_can_run_concurrently(self):
        def update_or_cleanup(index):
            scope = f"camera-{index % 4}"
            if index % 2:
                realtime_session_service.cleanup_presence_sessions(set(), scope)
            else:
                session_decision("check_in", self.recognized_item(), scope)

        with patch.object(realtime_session_service, "SESSION_STALE_SECONDS", -1):
            with ThreadPoolExecutor(max_workers=12) as executor:
                list(executor.map(update_or_cleanup, range(400)))


if __name__ == "__main__":
    unittest.main()

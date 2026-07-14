import unittest

from app.services import realtime_recognition_service as recognition


class RealtimeRecognitionServiceTests(unittest.TestCase):
    def setUp(self):
        recognition.face_embedding_cache.invalidate()
        self.original_can_log = recognition.can_log
        self.original_can_log_event = recognition.can_log_event
        self.original_log_access = recognition.log_access
        self.original_create_alert = recognition.create_alert
        self.original_save_evidence_image = recognition.save_evidence_image
        self.original_validate_transition = recognition.validate_attendance_transition
        self.original_liveness_history_note = recognition.liveness_history_note
        self.original_spoof_alert_message = recognition.spoof_alert_message

    def tearDown(self):
        recognition.face_embedding_cache.invalidate()
        recognition.can_log = self.original_can_log
        recognition.can_log_event = self.original_can_log_event
        recognition.log_access = self.original_log_access
        recognition.create_alert = self.original_create_alert
        recognition.save_evidence_image = self.original_save_evidence_image
        recognition.validate_attendance_transition = self.original_validate_transition
        recognition.liveness_history_note = self.original_liveness_history_note
        recognition.spoof_alert_message = self.original_spoof_alert_message

    @staticmethod
    def setting_getter(key, default=None):
        if key == "liveness_min_face_size":
            return 1
        return default

    @staticmethod
    def recognized_item():
        return {
            "bbox": [0, 0, 300, 300],
            "student_id": 7,
            "student_code": "SV007",
            "full_name": "Nguyen Van A",
            "confidence": 0.95,
            "recognized": True,
            "note": None,
        }

    @staticmethod
    def unknown_item():
        return {
            "bbox": [0, 0, 300, 300],
            "student_id": None,
            "student_code": "Unknown",
            "full_name": "Unknown",
            "confidence": None,
            "recognized": False,
            "note": None,
        }

    def process(
        self,
        items,
        decide_session,
        cleanup_sessions=lambda _keys, _scope: None,
        session_scope="test-source",
    ):
        return recognition.process_realtime_frame(
            object(),
            "check_in",
            "evidence-data",
            setting_getter=self.setting_getter,
            known_faces_loader=lambda: [],
            recognize_faces=lambda _image, _known, _threshold: items,
            cleanup_sessions=cleanup_sessions,
            decide_session=decide_session,
            session_scope=session_scope,
        )

    def test_multiple_actionable_faces_are_denied_without_logging(self):
        first = self.recognized_item()
        second = self.recognized_item() | {"student_id": 8, "student_code": "SV008", "bbox": [0, 0, 200, 200]}
        cleaned = []

        result = self.process(
            [first, second],
            lambda *_args: self.fail("must not decide"),
            lambda keys, scope: cleaned.append((keys, scope)),
        )

        self.assertEqual(result["items"][0]["decision"], "denied")
        self.assertEqual(result["items"][0]["warning_type"], "multiple_faces")
        self.assertEqual(result["items"][1]["decision"], "secondary")
        self.assertEqual(cleaned, [(set(), "test-source")])

    def test_success_logs_once_with_evidence_path(self):
        item = self.recognized_item()
        logs = []
        recognition.can_log = lambda *_args: True
        recognition.save_evidence_image = lambda _data: "evidence/test.jpg"
        recognition.log_access = lambda *args: logs.append(args)
        recognition.validate_attendance_transition = lambda *_args: (True, None)

        result = self.process([item], lambda *_args: ("success", "student:7:check_in", "success"))

        self.assertTrue(result["items"][0]["logged"])
        self.assertEqual(result["items"][0]["evidence_image_path"], "evidence/test.jpg")
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0][2], "success")

    def test_denied_face_creates_access_log_and_spoof_alert(self):
        item = self.recognized_item()
        logs = []
        alerts = []
        recognition.can_log_event = lambda *_args: True
        recognition.save_evidence_image = lambda _data: "evidence/test.jpg"
        recognition.log_access = lambda *args: logs.append(args)
        recognition.create_alert = lambda *args: alerts.append(args)
        recognition.validate_attendance_transition = lambda *_args: (True, None)
        recognition.liveness_history_note = lambda _item: ""
        recognition.spoof_alert_message = lambda _item: "Spoof detected"

        result = self.process([item], lambda *_args: ("denied", "student:7:check_in", "denied"))

        self.assertTrue(result["items"][0]["logged"])
        self.assertEqual(logs[0][2], "denied")
        self.assertEqual(alerts[0][0], "spoof_detected")

    def test_unknown_warning_creates_access_log_and_alert(self):
        item = self.unknown_item()
        logs = []
        alerts = []
        recognition.can_log_event = lambda *_args: True
        recognition.save_evidence_image = lambda _data: "evidence/test.jpg"
        recognition.log_access = lambda *args: logs.append(args)
        recognition.create_alert = lambda *args: alerts.append(args)

        result = self.process([item], lambda *_args: ("warning", "unknown:check_in", "warning"))

        self.assertTrue(result["items"][0]["logged"])
        self.assertEqual(logs[0][0], None)
        self.assertEqual(logs[0][2], "warning")
        self.assertEqual(alerts[0][0], "unknown_face")


if __name__ == "__main__":
    unittest.main()

import unittest


class RealtimeWebSocketSecurityTests(unittest.TestCase):
    def setUp(self):
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
            from starlette.websockets import WebSocketDisconnect
            import app.routers.realtime as realtime
            import app.services.realtime_recognition_service as recognition
        except ModuleNotFoundError as exc:
            self.skipTest(f"{exc.name} is not installed in this test environment.")

        self.FastAPI = FastAPI
        self.TestClient = TestClient
        self.WebSocketDisconnect = WebSocketDisconnect
        self.realtime = realtime
        self.recognition = recognition

        self.original_websocket_auth = realtime.websocket_auth
        self.original_load_known_faces = realtime.load_known_faces
        self.original_get_setting = realtime.get_setting
        self.original_parse_realtime_payload = realtime.parse_realtime_payload
        self.original_decode_realtime_image = realtime.decode_realtime_image
        self.original_recognize_faces = realtime.face_service.recognize_faces
        self.original_cleanup_presence_sessions = realtime.cleanup_presence_sessions
        self.original_clear_presence_scope = realtime.clear_presence_scope
        self.original_session_decision = realtime.session_decision
        self.original_allowed_origins = realtime.settings.websocket_allowed_origins
        self.original_max_message_bytes = realtime.settings.websocket_max_message_bytes
        self.original_validate_attendance_transition = (
            recognition.validate_attendance_transition
        )

        async def allow_websocket(_websocket):
            return True

        realtime.websocket_auth = allow_websocket
        realtime.load_known_faces = lambda: []
        realtime.get_setting = lambda key, default=None: "1" if key == "frame_skip" else default
        realtime.decode_realtime_image = lambda _image_data: object()
        realtime.settings.websocket_allowed_origins = "http://allowed.test"
        realtime.settings.websocket_max_message_bytes = 512 * 1024
        recognition.validate_attendance_transition = lambda _student_id, _action: (
            True,
            None,
        )

    def tearDown(self):
        realtime = getattr(self, "realtime", None)
        if not realtime:
            return
        realtime.websocket_auth = self.original_websocket_auth
        realtime.load_known_faces = self.original_load_known_faces
        realtime.get_setting = self.original_get_setting
        realtime.parse_realtime_payload = self.original_parse_realtime_payload
        realtime.decode_realtime_image = self.original_decode_realtime_image
        realtime.face_service.recognize_faces = self.original_recognize_faces
        realtime.cleanup_presence_sessions = self.original_cleanup_presence_sessions
        realtime.clear_presence_scope = self.original_clear_presence_scope
        realtime.session_decision = self.original_session_decision
        realtime.settings.websocket_allowed_origins = self.original_allowed_origins
        realtime.settings.websocket_max_message_bytes = self.original_max_message_bytes
        self.recognition.validate_attendance_transition = (
            self.original_validate_attendance_transition
        )

    def client(self):
        app = self.FastAPI()
        app.include_router(self.realtime.router)
        return self.TestClient(app, base_url="http://127.0.0.1")

    def test_rejects_cross_site_websocket_origin(self):
        client = self.client()

        with self.assertRaises(self.WebSocketDisconnect) as raised:
            with client.websocket_connect("/ws/recognize", headers={"origin": "https://evil.example"}):
                pass

        self.assertEqual(raised.exception.code, self.realtime.WS_POLICY_VIOLATION)

    def test_invalid_json_does_not_leak_parser_details(self):
        client = self.client()

        with client.websocket_connect("/ws/recognize", headers={"origin": "http://testserver"}) as websocket:
            websocket.send_text("{bad json")
            message = websocket.receive_json()

        self.assertEqual(message["type"], "error")
        self.assertEqual(message["code"], "invalid_payload")
        self.assertEqual(message["message"], self.realtime.SAFE_FRAME_ERROR_MESSAGE)
        self.assertNotIn("Expecting property name", message["message"])

    def test_oversized_message_is_rejected_and_closed(self):
        self.realtime.settings.websocket_max_message_bytes = 8
        client = self.client()

        with client.websocket_connect("/ws/recognize", headers={"origin": "http://testserver"}) as websocket:
            websocket.send_text("x" * 32)
            message = websocket.receive_json()
            self.assertEqual(message["code"], "message_too_large")

            with self.assertRaises(self.WebSocketDisconnect) as raised:
                websocket.receive_text()

        self.assertEqual(raised.exception.code, self.realtime.WS_MESSAGE_TOO_BIG)

    def test_unexpected_error_returns_generic_message(self):
        def fail_parse(_payload):
            raise RuntimeError("secret internal detail")

        self.realtime.parse_realtime_payload = fail_parse
        client = self.client()

        with self.assertLogs(self.realtime.logger, level="ERROR"):
            with client.websocket_connect("/ws/recognize", headers={"origin": "http://testserver"}) as websocket:
                websocket.send_text("{}")
                message = websocket.receive_json()

        self.assertEqual(message["type"], "error")
        self.assertEqual(message["code"], "internal_error")
        self.assertEqual(message["message"], self.realtime.SAFE_FRAME_ERROR_MESSAGE)
        self.assertNotIn("secret internal detail", message["message"])

    def test_recognized_face_result_contains_bbox_and_student_display_fields(self):
        self.realtime.face_service.recognize_faces = lambda _image, _known, _threshold: [
            {
                "bbox": [10, 20, 110, 150],
                "student_id": 42,
                "student_code": "SV042",
                "full_name": "Nguyen Van A",
                "confidence": 0.91,
                "recognized": True,
                "spoof_detected": False,
                "liveness_blocked": False,
                "liveness_status": "live",
                "quality_status": "ok",
                "liveness": None,
                "quality": {"ok": True, "reason": "ok"},
                "note": None,
            }
        ]
        self.realtime.session_decision = lambda _action, item, _scope: (
            None,
            f"student:{item['student_id']}:check_in",
            "pending",
        )
        client = self.client()

        with client.websocket_connect("/ws/recognize?action=check_in", headers={"origin": "http://testserver"}) as websocket:
            websocket.send_json({"image": "data:image/jpeg;base64,abc"})
            message = websocket.receive_json()

        self.assertEqual(message["type"], "result")
        item = message["items"][0]
        self.assertEqual(item["bbox"], [10, 20, 110, 150])
        self.assertTrue(item["recognized"])
        self.assertEqual(item["student_code"], "SV042")
        self.assertEqual(item["full_name"], "Nguyen Van A")
        self.assertEqual(item["display_status"], "pending")

    def test_unknown_face_result_still_contains_bbox_for_overlay(self):
        self.realtime.face_service.recognize_faces = lambda _image, _known, _threshold: [
            {
                "bbox": [30, 40, 130, 170],
                "student_id": None,
                "student_code": "Unknown",
                "full_name": "Unknown",
                "confidence": None,
                "recognized": False,
                "spoof_detected": False,
                "liveness_blocked": False,
                "liveness_status": "live",
                "quality_status": "ok",
                "liveness": None,
                "quality": {"ok": True, "reason": "ok"},
                "note": None,
            }
        ]
        self.realtime.session_decision = lambda _action, _item, _scope: (
            None,
            "unknown:check_in",
            "pending",
        )
        client = self.client()

        with client.websocket_connect("/ws/recognize?action=check_in", headers={"origin": "http://testserver"}) as websocket:
            websocket.send_json({"image": "data:image/jpeg;base64,abc"})
            message = websocket.receive_json()

        self.assertEqual(message["type"], "result")
        item = message["items"][0]
        self.assertEqual(item["bbox"], [30, 40, 130, 170])
        self.assertFalse(item["recognized"])
        self.assertEqual(item["full_name"], "Unknown")
        self.assertEqual(item["display_status"], "pending")

    def test_each_websocket_uses_and_clears_a_unique_session_scope(self):
        scopes = []
        cleared_scopes = []
        self.realtime.face_service.recognize_faces = lambda _image, _known, _threshold: [
            {
                "bbox": [30, 40, 130, 170],
                "student_id": None,
                "student_code": "Unknown",
                "full_name": "Unknown",
                "confidence": None,
                "recognized": False,
                "liveness_status": "live",
                "quality": {"ok": True},
                "note": None,
            }
        ]

        def decide(_action, _item, scope):
            scopes.append(scope)
            return None, f"{scope}:unknown:1:check_in", "pending"

        self.realtime.session_decision = decide
        self.realtime.clear_presence_scope = cleared_scopes.append
        client = self.client()

        for _ in range(2):
            with client.websocket_connect(
                "/ws/recognize?action=check_in",
                headers={"origin": "http://testserver"},
            ) as websocket:
                websocket.send_json({"image": "data:image/jpeg;base64,abc"})
                self.assertEqual(websocket.receive_json()["type"], "result")

        self.assertEqual(len(scopes), 2)
        self.assertNotEqual(scopes[0], scopes[1])
        self.assertTrue(all(scope.startswith("websocket:") for scope in scopes))
        self.assertCountEqual(cleared_scopes, scopes)

    def test_tiny_background_faces_do_not_block_primary_recognition(self):
        self.realtime.face_service.recognize_faces = lambda _image, _known, _threshold: [
            {
                "bbox": [10, 20, 130, 170],
                "student_id": 42,
                "student_code": "SV042",
                "full_name": "Nguyen Van A",
                "confidence": 0.91,
                "recognized": True,
                "spoof_detected": False,
                "liveness_blocked": False,
                "liveness_status": "live",
                "quality_status": "ok",
                "liveness": None,
                "quality": {"ok": True, "reason": "ok"},
                "note": None,
            },
            {
                "bbox": [200, 210, 225, 240],
                "student_id": None,
                "student_code": "Unknown",
                "full_name": "Unknown",
                "confidence": None,
                "recognized": False,
                "spoof_detected": False,
                "liveness_blocked": False,
                "liveness_status": "live",
                "quality_status": "face_too_small",
                "liveness": None,
                "quality": {"ok": False, "reason": "face_too_small"},
                "note": None,
            },
        ]
        self.realtime.session_decision = lambda _action, item, _scope: (
            None,
            f"student:{item['student_id']}:check_in",
            "pending",
        )
        client = self.client()

        with client.websocket_connect("/ws/recognize?action=check_in", headers={"origin": "http://testserver"}) as websocket:
            websocket.send_json({"image": "data:image/jpeg;base64,abc"})
            message = websocket.receive_json()

        self.assertEqual(message["type"], "result")
        self.assertEqual(len(message["items"]), 2)
        primary = next(item for item in message["items"] if item["student_code"] == "SV042")
        tiny = next(item for item in message["items"] if item["student_code"] == "Unknown")
        self.assertEqual(primary["display_status"], "pending")
        self.assertEqual(tiny["display_status"], "secondary")
        self.assertFalse(tiny["logged"])

    def test_multiple_actionable_faces_are_denied_without_logging(self):
        self.realtime.face_service.recognize_faces = lambda _image, _known, _threshold: [
            {
                "bbox": [10, 20, 130, 170],
                "student_id": 42,
                "student_code": "SV042",
                "full_name": "Nguyen Van A",
                "confidence": 0.91,
                "recognized": True,
                "spoof_detected": False,
                "liveness_blocked": False,
                "liveness_status": "live",
                "quality_status": "ok",
                "liveness": None,
                "quality": {"ok": True, "reason": "ok"},
                "note": None,
            },
            {
                "bbox": [180, 30, 300, 180],
                "student_id": 43,
                "student_code": "SV043",
                "full_name": "Tran Thi B",
                "confidence": 0.9,
                "recognized": True,
                "spoof_detected": False,
                "liveness_blocked": False,
                "liveness_status": "live",
                "quality_status": "ok",
                "liveness": None,
                "quality": {"ok": True, "reason": "ok"},
                "note": None,
            },
        ]
        client = self.client()

        with client.websocket_connect("/ws/recognize?action=check_in", headers={"origin": "http://testserver"}) as websocket:
            websocket.send_json({"image": "data:image/jpeg;base64,abc"})
            message = websocket.receive_json()

        self.assertEqual(message["type"], "result")
        primary = next(item for item in message["items"] if item["display_status"] != "secondary")
        self.assertEqual(primary["display_status"], "denied")
        self.assertEqual(primary["warning_type"], "multiple_faces")
        self.assertEqual(primary["display_full_name"], "Nguyen Van A")
        self.assertEqual(primary["note"], "Chi nen co 1 nguoi trong khung hinh de diem danh.")
        self.assertFalse(primary["logged"])
        self.assertTrue(all(not item["logged"] for item in message["items"]))


if __name__ == "__main__":
    unittest.main()

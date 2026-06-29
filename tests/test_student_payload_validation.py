import unittest
import sys
from types import SimpleNamespace

from pydantic import ValidationError

sys.modules.setdefault("cv2", SimpleNamespace())

try:
    from app.routers.students import StudentCreate
except ModuleNotFoundError as exc:
    if exc.name in {"fastapi", "cv2"}:
        raise unittest.SkipTest(f"{exc.name} is not installed in this test environment.")
    raise


class StudentPayloadValidationTests(unittest.TestCase):
    def test_student_create_trims_text_fields(self):
        payload = StudentCreate(
            student_code="  SV001  ",
            full_name="  Nguyen Van A  ",
            class_name="  CNTT  ",
            status=" ACTIVE ",
        )

        self.assertEqual(payload.student_code, "SV001")
        self.assertEqual(payload.full_name, "Nguyen Van A")
        self.assertEqual(payload.class_name, "CNTT")
        self.assertEqual(payload.status, "active")

    def test_student_create_rejects_empty_required_fields(self):
        with self.assertRaises(ValidationError):
            StudentCreate(student_code="   ", full_name="Nguyen Van A")

        with self.assertRaises(ValidationError):
            StudentCreate(student_code="SV001", full_name="   ")

    def test_student_create_rejects_unknown_status(self):
        with self.assertRaises(ValidationError):
            StudentCreate(student_code="SV001", full_name="Nguyen Van A", status="deleted")


if __name__ == "__main__":
    unittest.main()

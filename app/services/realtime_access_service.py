from app.services import access_event_service
from app.services.attendance_service import update_attendance_record
from app.services import attendance_transition_service
def validate_attendance_transition(student_id: int, action: str) -> tuple[bool, str | None]:
    return attendance_transition_service.validate_attendance_transition(student_id, action)


def seconds_since_last_success(student_id: int, action: str) -> float | None:
    return access_event_service.seconds_since_last_success(student_id, action)


def save_evidence_image(image_data: str | None) -> str | None:
    return access_event_service.save_evidence_image(image_data)


def log_access(student, action: str, result: str, confidence=None, note=None, evidence_image_path=None):
    access_event_service.log_access(
        student,
        action,
        result,
        confidence,
        note,
        evidence_image_path,
        update_attendance_record,
    )


def create_alert(alert_type: str, message: str, evidence_image_path=None, event_date: str | None = None):
    access_event_service.create_alert(alert_type, message, evidence_image_path, event_date)

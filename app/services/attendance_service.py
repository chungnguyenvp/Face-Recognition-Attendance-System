from datetime import datetime, timedelta
from app.services import (
    access_event_service,
    attendance_missing_checkout,
    attendance_record_service,
    attendance_transition_service,
)

_last_success = {}
_last_events = {}
def can_log_event(key: str, cooldown_seconds: int) -> bool:
    now = datetime.now()
    last = _last_events.get(key)
    if last and now - last < timedelta(seconds=cooldown_seconds):
        return False
    _last_events[key] = now
    return True


def can_log(student_id: int, action: str, cooldown_seconds: int) -> bool:
    key = f"{student_id}:{action}"
    now = datetime.now()
    last = _last_success.get(key)
    if last and now - last < timedelta(seconds=cooldown_seconds):
        return False
    _last_success[key] = now
    return True


def current_presence_state(student_id: int) -> str:
    return attendance_transition_service.current_presence_state(student_id)


def _attendance_status(
    attendance_date: str,
    first_check_in_at: str | None,
    last_check_out_at: str | None,
    missing_checkout: bool,
    config: dict | None = None,
    now: datetime | None = None,
    last_action: str | None = None,
) -> tuple[str, int, int, str | None]:
    return attendance_record_service.attendance_status(
        attendance_date,
        first_check_in_at,
        last_check_out_at,
        missing_checkout,
        config,
        now,
        last_action,
    )


def _attendance_note(status: str, summary: dict, fallback_note: str | None = None) -> str | None:
    return attendance_record_service.attendance_note(status, summary, fallback_note)


def _resolution_note(resolution_type: str | None, reason: str | None = None, checkout_at: str | None = None) -> str | None:
    return attendance_record_service.resolution_note(resolution_type, reason, checkout_at)


def _upsert_attendance_record(db, student, attendance_date: str, missing_checkout: bool | None = None) -> None:
    attendance_record_service.upsert_attendance_record(db, student, attendance_date, missing_checkout)


def attendance_record_context(db, student_id: int, attendance_date: str) -> dict:
    return attendance_record_service.attendance_record_context(db, student_id, attendance_date)


def attendance_record_detail(record_id: int) -> dict | None:
    return attendance_record_service.attendance_record_detail(record_id)


def resolve_missing_checkout_record(
    record_id: int,
    resolution_type: str,
    reason: str,
    checkout_time: str | None = None,
) -> dict | None:
    return attendance_missing_checkout.resolve_missing_checkout_record(
        record_id,
        resolution_type,
        reason,
        checkout_time,
    )


def update_attendance_record(student, action: str, event_time: datetime | None = None) -> None:
    attendance_record_service.update_attendance_record(student, action, event_time)


def ensure_attendance_records(attendance_date: str | None = None) -> int:
    return attendance_record_service.ensure_attendance_records(attendance_date)


def recalculate_attendance_records(date_from: str | None = None, date_to: str | None = None) -> int:
    mark_missing_checkouts()
    return attendance_record_service.recalculate_attendance_records(date_from, date_to)


def recalculate_student_attendance_records(student_id: int) -> int:
    mark_missing_checkouts()
    return attendance_record_service.recalculate_student_attendance_records(student_id)


def recalculate_student_attendance_record(student_id: int, attendance_date: str) -> bool:
    mark_missing_checkouts()
    return attendance_record_service.recalculate_student_attendance_record(student_id, attendance_date)


def mark_missing_checkouts(now: datetime | None = None, cutoff_value: str | None = None) -> int:
    return attendance_missing_checkout.mark_missing_checkouts(now, cutoff_value)


def mark_stale_checkin_missing_checkout(student_id: int, now: datetime | None = None) -> bool:
    return attendance_missing_checkout.mark_stale_checkin_missing_checkout(student_id, now)


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

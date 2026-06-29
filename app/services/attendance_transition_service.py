from datetime import datetime

from app.db import get_db
from app.repositories import access_log_repository
from app.services import attendance_missing_checkout
from app.services import attendance_calculation, work_schedule_service


def current_presence_state(student_id: int) -> str:
    with get_db() as db:
        row = access_log_repository.get_current_presence_action(db, student_id)
        if row and row["action"] == "check_in":
            checked_in_at = attendance_calculation.parse_log_time(row["created_at"])
            if checked_in_at and checked_in_at.date() < datetime.now().date() and not work_schedule_service.is_working_day(db, checked_in_at.date()):
                return "outside"
    if row and row["action"] == "check_in":
        return "inside"
    return "outside"


def validate_attendance_transition(student_id: int, action: str) -> tuple[bool, str | None]:
    state = current_presence_state(student_id)
    if action == "check_in" and state == "inside":
        if attendance_missing_checkout.mark_stale_checkin_missing_checkout(student_id):
            return True, None
        return False, "Sinh viên đã check-in, chưa check-out."
    if action == "check_out" and state == "outside":
        return False, "Sinh viên chưa check-in, không thể check-out."
    return True, None

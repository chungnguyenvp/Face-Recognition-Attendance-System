from __future__ import annotations

from datetime import date, datetime

from app.repositories import leave_repository, student_repository
from app.services.attendance_record_service import recalculate_student_attendance_range
from app.services.audit_service import write_audit_log
from app.services import work_schedule_service


def _now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _leave_label(leave) -> str:
    return f"{leave['student_code']} - {leave['full_name']} ({leave['start_date']} to {leave['end_date']})"


def _audit_details(leave, status: str, reviewer_note: str | None = None) -> dict:
    details = {
        "leave_type": leave["leave_type"],
        "start_date": leave["start_date"],
        "end_date": leave["end_date"],
        "status": status,
    }
    if reviewer_note:
        details["reviewer_note"] = reviewer_note
    return details


def create_leave_request(db, actor: dict, payload, request=None) -> dict:
    student_id = actor.get("student_id")
    if not student_id:
        raise ValueError("Tai khoan chua lien ket voi sinh vien.")
    student = student_repository.get_student_by_id(db, student_id)
    if not student or student["status"] != "active":
        raise ValueError("Ho so sinh vien khong con hoat dong.")
    if payload.start_date < date.today():
        raise ValueError("Chi duoc tao don nghi tu ngay hom nay tro di.")
    start_date, end_date = payload.start_date.isoformat(), payload.end_date.isoformat()
    if not work_schedule_service.working_days_between(db, payload.start_date, payload.end_date):
        raise ValueError("Khoảng thời gian đã chọn không có ngày làm việc, không cần tạo đơn nghỉ.")
    db.execute("BEGIN IMMEDIATE")
    if leave_repository.has_overlapping_leave_request(db, student_id, start_date, end_date):
        raise ValueError("Ban da co don nghi trung thoi gian dang cho xu ly hoac da duyet.")
    now_text = _now_text()
    leave_id = leave_repository.create_leave_request(db, student_id, payload.leave_type, start_date, end_date, payload.reason, now_text)
    leave = leave_repository.get_leave_request_by_id(db, leave_id)
    recalculate_student_attendance_range(db, student_id, start_date, end_date)
    write_audit_log(
        db, actor, "leave_requests.create", "leave_request", leave_id, _leave_label(leave),
        _audit_details(leave, "pending"), request,
    )
    return dict(leave_repository.get_leave_request_by_id(db, leave_id))


def review_leave_request(db, actor: dict, leave_id: int, status: str, reviewer_note: str | None, request=None) -> dict:
    leave = leave_repository.get_leave_request_by_id(db, leave_id)
    if not leave:
        raise LookupError("Khong tim thay don nghi.")
    if not leave_repository.update_pending_review(db, leave_id, status, actor["id"], reviewer_note, _now_text()):
        raise ValueError("Chi co the xu ly don dang cho duyet.")
    recalculate_student_attendance_range(db, leave["student_id"], leave["start_date"], leave["end_date"])
    write_audit_log(
        db, actor, f"leave_requests.{status}", "leave_request", leave_id, _leave_label(leave),
        _audit_details(leave, status, reviewer_note), request,
    )
    return dict(leave_repository.get_leave_request_by_id(db, leave_id))


def cancel_leave_request(db, actor: dict, leave_id: int, request=None) -> dict:
    leave = leave_repository.get_leave_request_by_id(db, leave_id)
    if not leave:
        raise LookupError("Khong tim thay don nghi.")
    if leave["student_id"] != actor.get("student_id"):
        raise PermissionError("Ban khong co quyen huy don nay.")
    if not leave_repository.cancel_pending_leave_request(db, leave_id, _now_text()):
        raise ValueError("Chi co the huy don dang cho duyet.")
    recalculate_student_attendance_range(db, leave["student_id"], leave["start_date"], leave["end_date"])
    write_audit_log(
        db, actor, "leave_requests.cancel", "leave_request", leave_id, _leave_label(leave),
        _audit_details(leave, "cancelled"), request,
    )
    return dict(leave_repository.get_leave_request_by_id(db, leave_id))


def revoke_leave_request(db, actor: dict, leave_id: int, reviewer_note: str, request=None) -> dict:
    leave = leave_repository.get_leave_request_by_id(db, leave_id)
    if not leave:
        raise LookupError("Khong tim thay don nghi.")
    if not leave_repository.revoke_approved_leave_request(db, leave_id, actor["id"], reviewer_note, _now_text()):
        raise ValueError("Chi co the thu hoi don da duyet.")
    recalculate_student_attendance_range(db, leave["student_id"], leave["start_date"], leave["end_date"])
    write_audit_log(
        db, actor, "leave_requests.revoke", "leave_request", leave_id, _leave_label(leave),
        _audit_details(leave, "revoked", reviewer_note), request,
    )
    return dict(leave_repository.get_leave_request_by_id(db, leave_id))

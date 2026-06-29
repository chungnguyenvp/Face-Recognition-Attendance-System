from datetime import datetime, time, timedelta

from app.db import get_db, get_setting
from app.repositories import attendance_repository, leave_repository, student_repository
from app.services import attendance_calculation
from app.services import work_schedule_service


DEFAULT_WORK_START_TIME = "08:00"
DEFAULT_WORK_END_TIME = "17:00"
DEFAULT_LATE_GRACE_MINUTES = 5
DEFAULT_EARLY_LEAVE_GRACE_MINUTES = 10


def student_attendance_config(db, student_id: int, attendance_date: str | None = None) -> dict:
    row = attendance_repository.get_student_attendance_config(db, student_id)
    policy = work_schedule_service.get_day_policy(db, attendance_date)
    schedule = policy["config"]
    return {
        "work_start_time": _parse_time_value(
            row["work_start_time"] if row else None,
            schedule.get("start_time", DEFAULT_WORK_START_TIME),
        ),
        "work_end_time": _parse_time_value(
            row["work_end_time"] if row else None,
            schedule.get("end_time", DEFAULT_WORK_END_TIME),
        ),
        "late_grace_minutes": int(schedule.get("late_allowed_minutes", DEFAULT_LATE_GRACE_MINUTES)),
        "early_leave_grace_minutes": int(schedule.get("early_leave_allowed_minutes", DEFAULT_EARLY_LEAVE_GRACE_MINUTES)),
    }


def attendance_day_summary(db, student_id: int, attendance_date: str) -> dict:
    rows = attendance_repository.list_attendance_day_logs(db, student_id, attendance_date)
    return attendance_calculation.summarize_day_logs(rows)


def attendance_status(
    attendance_date: str,
    first_check_in_at: str | None,
    last_check_out_at: str | None,
    missing_checkout: bool,
    config: dict | None = None,
    now: datetime | None = None,
    last_action: str | None = None,
    leave_status: str | None = None,
) -> tuple[str, int, int, str | None]:
    first_check_in = attendance_calculation.parse_log_time(first_check_in_at)
    last_check_out = attendance_calculation.parse_log_time(last_check_out_at)
    active_config = config or _default_attendance_config()
    start_time = active_config["work_start_time"]
    end_time = active_config["work_end_time"]
    late_grace = active_config["late_grace_minutes"]
    early_grace = active_config["early_leave_grace_minutes"]

    if not first_check_in:
        if leave_status == "approved":
            return "leave_approved", 0, 0, "Nghi co phep."
        if leave_status == "pending":
            return "leave_pending", 0, 0, "Don nghi dang cho duyet."
        if _workday_has_ended(attendance_date, end_time, now):
            return "absent", 0, 0, "Không có check-in trong ngày."
        return "pending", 0, 0, "Chưa có check-in."

    late_after = attendance_calculation.combine_date_time(attendance_date, start_time) + timedelta(minutes=late_grace)
    late_minutes = attendance_calculation.ceil_minutes(first_check_in - late_after) if first_check_in > late_after else 0

    early_leave_minutes = 0
    workday_ended = _workday_has_ended(attendance_date, end_time, now)
    if last_check_out and last_action == "check_out" and workday_ended:
        early_before = attendance_calculation.combine_date_time(attendance_date, end_time) - timedelta(minutes=early_grace)
        if last_check_out < early_before:
            early_leave_minutes = attendance_calculation.ceil_minutes(early_before - last_check_out)

    if missing_checkout:
        return "missing_checkout", late_minutes, early_leave_minutes, "Đã check-in nhưng chưa check-out."
    if not workday_ended or last_action == "check_in":
        return "unfinalized", late_minutes, 0, None
    if late_minutes and early_leave_minutes:
        return "late_and_early_leave", late_minutes, early_leave_minutes, None
    if late_minutes:
        return "late", late_minutes, early_leave_minutes, None
    if early_leave_minutes:
        return "early_leave", late_minutes, early_leave_minutes, None
    return "present_on_time", late_minutes, early_leave_minutes, None


def attendance_note(status: str, summary: dict, fallback_note: str | None = None) -> str | None:
    if fallback_note:
        return fallback_note
    if status == "leave_approved":
        return "Nghi co phep."
    if status == "leave_pending":
        return "Don nghi dang cho duyet."
    if status == "absent":
        return "Không có check-in trong ngày."
    if status == "pending":
        return "Chưa có check-in."
    if status == "missing_checkout":
        return "Đã check-in nhưng chưa check-out."

    current_out_since = attendance_calculation.parse_log_time(summary.get("current_out_since_at"))
    outside_count = int(summary.get("outside_count") or 0)
    outside_minutes = int(summary.get("outside_minutes") or 0)
    if status in {"early_leave", "late_and_early_leave"} and current_out_since:
        note = f"Ra cuối lúc {attendance_calculation.time_text(current_out_since)}, không quay lại."
        if outside_count:
            note += f" Đã ra ngoài {outside_count} lần, tổng {attendance_calculation.duration_text(outside_minutes)}."
        return note
    if current_out_since:
        return f"Đã ra ngoài từ {attendance_calculation.time_text(current_out_since)}."
    if outside_count:
        return f"Đã ra ngoài {outside_count} lần, tổng {attendance_calculation.duration_text(outside_minutes)}."
    if status == "unfinalized":
        return "Đã check-in, chưa chốt ca."
    return None


def resolution_note(resolution_type: str | None, reason: str | None = None, checkout_at: str | None = None) -> str | None:
    clean_reason = (reason or "").strip()
    suffix = f" Lý do: {clean_reason}" if clean_reason else ""
    checkout_time = attendance_calculation.time_text(attendance_calculation.parse_log_time(checkout_at))
    if resolution_type == "auto_work_end":
        return f"Tự chốt check-out theo giờ kết thúc ca lúc {checkout_time} do thiếu check-out."
    if resolution_type == "keep_zero":
        return f"Giữ thiếu check-out, tính 0h.{suffix}"
    if resolution_type == "work_end":
        return f"Admin chốt check-out theo giờ kết thúc ca lúc {checkout_time}.{suffix}"
    if resolution_type == "manual_time":
        return f"Admin nhập giờ ra {checkout_time} do thiếu check-out.{suffix}"
    return None


def upsert_attendance_record(db, student, attendance_date: str, missing_checkout: bool | None = None) -> None:
    student_id = student["student_id"] if "student_id" in student.keys() else student["id"]
    existing = attendance_repository.get_attendance_record_by_student_date(db, student_id, attendance_date)
    summary = attendance_day_summary(db, student_id, attendance_date)
    first_check_in_at = summary["first_check_in_at"]
    last_check_out_at = summary["last_check_out_at"]
    total_minutes = summary["total_minutes"]
    current_missing = bool(existing["missing_checkout"]) if existing else False
    next_missing = bool(missing_checkout) if missing_checkout is not None else current_missing
    if last_check_out_at and missing_checkout is None:
        next_missing = False
    policy = work_schedule_service.get_day_policy(db, attendance_date)
    if not policy["is_working_day"]:
        if not existing and not first_check_in_at and not last_check_out_at:
            return
        now_text = datetime.now().isoformat(timespec="seconds")
        note = f"{policy['label']} - không tính chuyên cần."
        if existing:
            attendance_repository.update_attendance_record_summary(
                db, existing["id"], student["student_code"], student["full_name"], first_check_in_at,
                last_check_out_at, "off_day", 0, 0, total_minutes, False, note, now_text,
            )
            return
        attendance_repository.create_attendance_record(
            db, student_id, student["student_code"], student["full_name"], attendance_date,
            first_check_in_at, last_check_out_at, "off_day", 0, 0, total_minutes, False,
            note, now_text, now_text,
        )
        return
    leave_status = leave_repository.find_leave_status_for_student_on_date(db, student_id, attendance_date)
    status, late_minutes, early_leave_minutes, note = attendance_status(
        attendance_date,
        first_check_in_at,
        last_check_out_at,
        next_missing,
        student_attendance_config(db, student_id, attendance_date),
        last_action=summary["last_action"],
        leave_status=leave_status,
    )
    note = attendance_note(status, summary, note)
    resolution_type = existing["missing_checkout_resolution"] if existing and "missing_checkout_resolution" in existing.keys() else None
    resolution_reason = existing["resolution_reason"] if existing and "resolution_reason" in existing.keys() else None
    resolution_checkout_at = existing["resolution_checkout_at"] if existing and "resolution_checkout_at" in existing.keys() else None
    force_zero = bool(existing["force_zero_minutes"]) if existing and "force_zero_minutes" in existing.keys() else False
    if resolution_type == "keep_zero" and force_zero:
        status = "missing_checkout"
        total_minutes = 0
        next_missing = True
        note = resolution_note(resolution_type, resolution_reason)
    elif resolution_type in {"work_end", "manual_time", "auto_work_end"}:
        note = resolution_note(resolution_type, resolution_reason, resolution_checkout_at)
    now_text = datetime.now().isoformat(timespec="seconds")
    student_code = student["student_code"]
    full_name = student["full_name"]

    if existing:
        attendance_repository.update_attendance_record_summary(
            db,
            existing["id"],
            student_code,
            full_name,
            first_check_in_at,
            last_check_out_at,
            status,
            late_minutes,
            early_leave_minutes,
            total_minutes,
            next_missing,
            note,
            now_text,
        )
        return

    attendance_repository.create_attendance_record(
        db,
        student_id,
        student_code,
        full_name,
        attendance_date,
        first_check_in_at,
        last_check_out_at,
        status,
        late_minutes,
        early_leave_minutes,
        total_minutes,
        next_missing,
        note,
        now_text,
        now_text,
    )


def attendance_record_context(db, student_id: int, attendance_date: str) -> dict:
    return attendance_day_summary(db, student_id, attendance_date)


def attendance_record_detail(record_id: int) -> dict | None:
    with get_db() as db:
        record = attendance_repository.get_attendance_record_by_id(db, record_id)
        if not record:
            return None
        summary = attendance_day_summary(db, record["student_id"], record["attendance_date"])
        return {
            "record": {
                "id": record["id"],
                "student_id": record["student_id"],
                "student_code": record["student_code"],
                "full_name": record["full_name"],
                "attendance_date": record["attendance_date"],
                "status": record["status"],
                "late_minutes": record["late_minutes"],
                "early_leave_minutes": record["early_leave_minutes"],
                "total_minutes": record["total_minutes"],
                "note": record["note"],
                "missing_checkout_resolution": record["missing_checkout_resolution"] if "missing_checkout_resolution" in record.keys() else None,
                "resolution_reason": record["resolution_reason"] if "resolution_reason" in record.keys() else None,
                "resolution_checkout_at": record["resolution_checkout_at"] if "resolution_checkout_at" in record.keys() else None,
                "force_zero_minutes": record["force_zero_minutes"] if "force_zero_minutes" in record.keys() else 0,
            },
            "summary": summary,
        }


def update_attendance_record(student, action: str, event_time: datetime | None = None) -> None:
    if not student or action not in {"check_in", "check_out"}:
        return
    student_id = student.get("student_id") or student.get("id")
    if not student_id:
        return
    event_at = event_time or datetime.now()
    attendance_date = attendance_calculation.date_text(event_at)
    with get_db() as db:
        row = student_repository.get_student_identity(db, student_id)
        if row:
            upsert_attendance_record(db, row, attendance_date)


def ensure_attendance_records(attendance_date: str | None = None) -> int:
    target_date = attendance_date or attendance_calculation.date_text(datetime.now())
    with get_db() as db:
        return recalculate_attendance_date(db, target_date)


def recalculate_attendance_date(db, attendance_date: str) -> int:
    students = student_repository.list_active_student_identities(db)
    for student in students:
        upsert_attendance_record(db, student, attendance_date)
    return len(students)


def recalculate_attendance_records(date_from: str | None = None, date_to: str | None = None) -> int:
    start = datetime.fromisoformat(date_from).date() if date_from else datetime.now().date()
    end = datetime.fromisoformat(date_to).date() if date_to else start
    if end < start:
        start, end = end, start
    created_or_updated = 0
    current = start
    while current <= end:
        created_or_updated += ensure_attendance_records(current.isoformat())
        current += timedelta(days=1)
    return created_or_updated


def recalculate_student_attendance_records(student_id: int) -> int:
    with get_db() as db:
        student = student_repository.get_student_identity(db, student_id)
        if not student:
            return 0
        rows = attendance_repository.list_student_attendance_dates(db, student_id)
        for row in rows:
            upsert_attendance_record(db, student, row["date_text"])
    return len(rows)


def recalculate_student_attendance_record(student_id: int, attendance_date: str) -> bool:
    with get_db() as db:
        student = student_repository.get_student_identity(db, student_id)
        if not student:
            return False
        upsert_attendance_record(db, student, attendance_date)
    return True


def recalculate_student_attendance_range(db, student_id: int, start_date: str, end_date: str) -> int:
    student = student_repository.get_student_identity(db, student_id)
    if not student:
        return 0
    current = datetime.fromisoformat(start_date).date()
    end = datetime.fromisoformat(end_date).date()
    updated = 0
    while current <= end:
        upsert_attendance_record(db, student, current.isoformat())
        updated += 1
        current += timedelta(days=1)
    return updated


def _default_attendance_config() -> dict:
    return {
        "work_start_time": _setting_time("work_start_time", DEFAULT_WORK_START_TIME),
        "work_end_time": _setting_time("work_end_time", DEFAULT_WORK_END_TIME),
        "late_grace_minutes": _setting_int("late_grace_minutes", DEFAULT_LATE_GRACE_MINUTES),
        "early_leave_grace_minutes": _setting_int("early_leave_grace_minutes", DEFAULT_EARLY_LEAVE_GRACE_MINUTES),
    }


def _workday_has_ended(attendance_date: str, work_end: time, now: datetime | None = None) -> bool:
    return (now or datetime.now()) >= attendance_calculation.combine_date_time(attendance_date, work_end)


def _setting_int(key: str, default: int) -> int:
    try:
        return int(get_setting(key, default))
    except (TypeError, ValueError):
        return default


def _setting_time(key: str, default: str) -> time:
    return _parse_time_value(get_setting(key, default), default)


def _parse_time_value(value: str | None, default: str) -> time:
    raw = (value or default).strip()
    try:
        hour_text, minute_text = raw.split(":", 1)
        return time(hour=int(hour_text), minute=int(minute_text))
    except (TypeError, ValueError):
        return time(hour=23, minute=59)

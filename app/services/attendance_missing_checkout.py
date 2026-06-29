from datetime import datetime, time, timedelta

from app.db import get_db, get_setting
from app.repositories import alert_repository, access_log_repository, attendance_repository, student_repository
from app.services.attendance_calculation import combine_date_time, date_text, parse_log_time
from app.services import attendance_record_service
from app.services import work_schedule_service


MISSING_CHECKOUT_ALERT_TYPE = "missing_checkout"
DEFAULT_MISSING_CHECKOUT_CUTOFF_TIME = "23:59"
AUTO_CLOSE_REASON = "Hệ thống tự chốt do quá giờ chốt thiếu check-out."


def parse_manual_checkout_time(attendance_date: str, checkout_time: str) -> datetime:
    try:
        hour_text, minute_text = (checkout_time or "").split(":", 1)
        checkout = time(hour=int(hour_text), minute=int(minute_text))
    except (TypeError, ValueError):
        raise ValueError("Giờ ra không hợp lệ.")
    return combine_date_time(attendance_date, checkout)


def missing_checkout_message(checkin_log) -> str:
    created_at = parse_log_time(checkin_log["created_at"])
    if created_at:
        day_text = created_at.strftime("%d/%m/%Y")
        time_value = created_at.strftime("%H:%M")
    else:
        day_text = checkin_log["created_at"] or "không rõ ngày"
        time_value = "--:--"
    student_code = checkin_log["student_code"] or "Unknown"
    return f"Sinh viên {student_code} đã check-in ngày {day_text} lúc {time_value} nhưng chưa check-out."


def missing_checkout_dedupe_tokens(checkin_log) -> tuple[str, str]:
    created_at = parse_log_time(checkin_log["created_at"])
    day_text = created_at.strftime("%d/%m/%Y") if created_at else (checkin_log["created_at"] or "không rõ ngày")
    student_code = checkin_log["student_code"] or "Unknown"
    return student_code, day_text


def missing_checkout_event_date(checkin_log) -> str:
    created_at = parse_log_time(checkin_log["created_at"])
    return date_text(created_at) if created_at else datetime.now().date().isoformat()


def missing_checkout_alert_at(checkin_log, cutoff_value: str) -> datetime:
    created_at = parse_log_time(checkin_log["created_at"])
    if not created_at:
        return datetime.now()
    try:
        hour_text, minute_text = cutoff_value.strip().split(":", 1)
        cutoff_time = time(hour=int(hour_text), minute=int(minute_text))
    except (AttributeError, TypeError, ValueError):
        cutoff_time = time(hour=23, minute=59)
    alert_at = datetime.combine(created_at.date(), cutoff_time)
    if created_at > alert_at:
        alert_at += timedelta(days=1)
    return alert_at


def resolve_missing_checkout_record(
    record_id: int,
    resolution_type: str,
    reason: str,
    checkout_time: str | None = None,
) -> dict | None:
    clean_reason = (reason or "").strip()
    if not clean_reason:
        raise ValueError("Vui lòng nhập lý do xử lý thiếu check-out.")
    if resolution_type not in {"work_end", "manual_time", "keep_zero"}:
        raise ValueError("Cách xử lý thiếu check-out không hợp lệ.")

    now_text = datetime.now().isoformat(timespec="seconds")
    with get_db() as db:
        record = attendance_repository.get_attendance_record_by_id(db, record_id)
        if not record:
            return None
        current_resolution = _resolution_type(record)
        if record["status"] != "missing_checkout" and current_resolution not in {
            "auto_work_end",
            "work_end",
            "manual_time",
            "keep_zero",
        }:
            raise ValueError("Chỉ xử lý được bản ghi thiếu check-out hoặc đã chốt do thiếu check-out.")
        student = student_repository.get_student_identity(db, record["student_id"])
        if not student:
            return None

        _delete_resolution_checkout_log(db, record)
        attendance_repository.clear_missing_checkout_resolution(db, record_id)
        if resolution_type == "keep_zero":
            attendance_record_service.upsert_attendance_record(
                db,
                student,
                record["attendance_date"],
                missing_checkout=True,
            )
            attendance_repository.set_missing_checkout_keep_zero_resolution(
                db,
                record_id,
                attendance_record_service.resolution_note("keep_zero", clean_reason),
                resolution_type,
                clean_reason,
                now_text,
            )
        else:
            if resolution_type == "work_end":
                work_end = attendance_record_service.student_attendance_config(
                    db,
                    record["student_id"],
                    record["attendance_date"],
                )["work_end_time"]
                checkout_at = combine_date_time(record["attendance_date"], work_end)
            else:
                if not checkout_time:
                    raise ValueError("Vui lòng nhập giờ ra.")
                checkout_at = parse_manual_checkout_time(record["attendance_date"], checkout_time)

            summary = attendance_record_service.attendance_day_summary(
                db,
                record["student_id"],
                record["attendance_date"],
            )
            open_check_in = parse_log_time(summary.get("open_check_in_at"))
            if open_check_in and checkout_at < open_check_in:
                raise ValueError("Giờ ra phải sau lần check-in cuối cùng.")

            checkout_at_text = checkout_at.isoformat(timespec="seconds")
            note = attendance_record_service.resolution_note(
                resolution_type,
                clean_reason,
                checkout_at_text,
            )
            access_log_repository.create_access_log(
                db,
                student["id"],
                student["student_code"],
                student["full_name"],
                "check_out",
                "success",
                None,
                note,
                None,
                checkout_at_text,
            )
            attendance_repository.set_missing_checkout_resolution(
                db,
                record_id,
                resolution_type,
                clean_reason,
                checkout_at_text,
                now_text,
            )
            attendance_record_service.upsert_attendance_record(db, student, record["attendance_date"])

        updated = attendance_repository.get_attendance_record_by_id(db, record_id)
        return dict(updated) if updated else None


def mark_missing_checkouts(now: datetime | None = None, cutoff_value: str | None = None) -> int:
    current = now or datetime.now()
    with get_db() as db:
        rows = access_log_repository.list_successful_check_events_until(
            db,
            current.isoformat(timespec="seconds"),
        )
        open_checkins = {}
        created = 0
        for row in rows:
            student_id = row["student_id"]
            if row["action"] == "check_out":
                open_checkins.pop(student_id, None)
                continue

            previous = open_checkins.get(student_id)
            previous_at = parse_log_time(previous["created_at"]) if previous else None
            current_at = parse_log_time(row["created_at"])
            if previous and previous_at and current_at and previous_at.date() != current_at.date():
                previous_date = date_text(previous_at)
                alert_at = missing_checkout_alert_at(previous, _cutoff_for(db, previous_date, cutoff_value))
                if alert_at <= current and _finalize_missing_checkout(db, previous, date_text(previous_at), alert_at):
                    created += 1
            if current_at and not work_schedule_service.is_working_day(db, current_at.date()):
                continue
            open_checkins[student_id] = row

        for row in open_checkins.values():
            created_at = parse_log_time(row["created_at"])
            if not created_at or not work_schedule_service.is_working_day(db, created_at.date()):
                continue
            alert_at = missing_checkout_alert_at(row, _cutoff_for(db, date_text(created_at), cutoff_value))
            if created_at and alert_at <= current:
                if _finalize_missing_checkout(db, row, date_text(created_at), alert_at):
                    created += 1
        return created


def mark_stale_checkin_missing_checkout(student_id: int, now: datetime | None = None) -> bool:
    current = now or datetime.now()
    with get_db() as db:
        row = access_log_repository.get_last_success_check_event(db, student_id)
        if not row or row["action"] != "check_in":
            return False
        created_at = parse_log_time(row["created_at"])
        if not created_at or created_at.date() >= current.date():
            return False
        _finalize_missing_checkout(db, row, date_text(created_at))
        return True


def _finalize_missing_checkout(db, checkin_log, attendance_date: str, alert_at: datetime | None = None) -> bool:
    if not work_schedule_service.is_working_day(db, attendance_date):
        attendance_record_service.upsert_attendance_record(db, checkin_log, attendance_date, missing_checkout=False)
        return False
    if not _auto_close_open_checkin(db, checkin_log, attendance_date):
        attendance_record_service.upsert_attendance_record(
            db,
            checkin_log,
            attendance_date,
            missing_checkout=True,
        )
    return _create_missing_checkout_alert(db, checkin_log, alert_at)


def _auto_close_open_checkin(db, checkin_log, attendance_date: str) -> bool:
    student_id = checkin_log["student_id"]
    if student_id is None:
        return False
    existing = attendance_repository.get_attendance_record_by_student_date(db, student_id, attendance_date)
    if existing:
        resolution = _resolution_type(existing)
        force_zero = bool(existing["force_zero_minutes"]) if "force_zero_minutes" in existing.keys() else False
        if resolution in {"keep_zero", "work_end", "manual_time", "auto_work_end"} or force_zero:
            return False

    summary = attendance_record_service.attendance_day_summary(db, student_id, attendance_date)
    if summary.get("last_action") != "check_in":
        return False
    open_check_in = parse_log_time(summary.get("open_check_in_at"))
    if not open_check_in:
        return False
    config = attendance_record_service.student_attendance_config(db, student_id, attendance_date)
    checkout_at = combine_date_time(attendance_date, config["work_end_time"])
    if checkout_at < open_check_in:
        return False

    checkout_at_text = checkout_at.isoformat(timespec="seconds")
    note = attendance_record_service.resolution_note(
        "auto_work_end",
        AUTO_CLOSE_REASON,
        checkout_at_text,
    )
    access_log_repository.create_access_log(
        db,
        student_id,
        checkin_log["student_code"],
        checkin_log["full_name"],
        "check_out",
        "success",
        None,
        note,
        None,
        checkout_at_text,
    )
    attendance_record_service.upsert_attendance_record(db, checkin_log, attendance_date)
    attendance_repository.set_auto_work_end_missing_checkout_resolution(
        db,
        student_id,
        attendance_date,
        AUTO_CLOSE_REASON,
        checkout_at_text,
        note,
        datetime.now().isoformat(timespec="seconds"),
    )
    return True


def _create_missing_checkout_alert(db, checkin_log, alert_at: datetime | None = None) -> bool:
    message = missing_checkout_message(checkin_log)
    student_code, day_text = missing_checkout_dedupe_tokens(checkin_log)
    event_date = missing_checkout_event_date(checkin_log)
    alert_time = alert_at or missing_checkout_alert_at(
        checkin_log,
        _cutoff_for(db, event_date),
    )
    existing = alert_repository.get_alert_by_type_and_message_tokens(
        db,
        MISSING_CHECKOUT_ALERT_TYPE,
        student_code,
        day_text,
    )
    if existing:
        return False
    alert_repository.create_alert(
        db,
        MISSING_CHECKOUT_ALERT_TYPE,
        message,
        None,
        event_date,
        alert_time.isoformat(timespec="seconds"),
    )
    return True


def _cutoff_for(db, attendance_date: str, fallback: str | None = None) -> str:
    if fallback:
        return fallback
    policy = work_schedule_service.get_day_policy(db, attendance_date)
    return policy["config"].get("checkout_cutoff_time") or get_setting(
        "missing_checkout_cutoff_time", DEFAULT_MISSING_CHECKOUT_CUTOFF_TIME,
    )


def _resolution_type(record) -> str | None:
    return record["missing_checkout_resolution"] if "missing_checkout_resolution" in record.keys() else None


def _delete_resolution_checkout_log(db, record) -> None:
    resolution_type = _resolution_type(record)
    if resolution_type not in {"auto_work_end", "work_end", "manual_time"}:
        return
    checkout_at = record["resolution_checkout_at"] if "resolution_checkout_at" in record.keys() else None
    if checkout_at:
        access_log_repository.delete_successful_check_out_at(db, record["student_id"], checkout_at)

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, time, timedelta

from app.repositories import work_schedule_repository


WEEKDAY_FIELDS = (
    "monday_enabled", "tuesday_enabled", "wednesday_enabled", "thursday_enabled",
    "friday_enabled", "saturday_enabled", "sunday_enabled",
)
WEEKDAY_LABELS = ("Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật")


def date_value(value: date | str | None = None) -> date:
    if value is None:
        return datetime.now().date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def get_day_policy(db, value: date | str | None = None) -> dict:
    target = date_value(value)
    target_text = target.isoformat()
    schedule = work_schedule_repository.get_schedule_for_date(db, target_text)
    exception = work_schedule_repository.get_exception_for_date(db, target_text)

    if exception and exception["exception_type"] == "off":
        return _policy(db, target, schedule, False, "special_holiday", exception)
    if exception and exception["exception_type"] == "working":
        return _policy(db, target, schedule, True, "special_working_day", exception)

    enabled = bool(schedule[WEEKDAY_FIELDS[target.weekday()]]) if schedule else True
    return _policy(db, target, schedule, enabled, "working_day" if enabled else "weekend_off", None)


def is_working_day(db, value: date | str | None = None) -> bool:
    return bool(get_day_policy(db, value)["is_working_day"])


def working_days_between(db, start: date | str, end: date | str) -> list[date]:
    current, final = date_value(start), date_value(end)
    result = []
    while current <= final:
        if is_working_day(db, current):
            result.append(current)
        current += timedelta(days=1)
    return result


def calendar_preview(db, year: int, month: int) -> list[dict]:
    result = []
    for day in range(1, monthrange(year, month)[1] + 1):
        policy = get_day_policy(db, date(year, month, day))
        result.append({
            "date": policy["date"], "day": day, "weekday": policy["weekday"],
            "status": policy["status"], "is_working_day": policy["is_working_day"],
            "label": policy["label"], "holiday_name": policy.get("holiday_name"),
        })
    return result


def schedule_payload(db, value: date | str | None = None) -> dict:
    target = date_value(value)
    row = work_schedule_repository.get_schedule_for_date(db, target.isoformat())
    if not row:
        return _fallback_schedule(target)
    return _config_dict(db, row)


def policy_time(value: str) -> time:
    return time.fromisoformat(value)


def _policy(db, target: date, schedule, is_working: bool, status: str, exception) -> dict:
    labels = {
        "working_day": "Ngày làm việc",
        "weekend_off": "Ngày nghỉ theo lịch tuần",
        "special_holiday": exception["holiday_name"] if exception else "Ngày nghỉ đặc biệt",
        "special_working_day": exception["holiday_name"] if exception else "Ngày làm việc đặc biệt",
    }
    config = _config_dict(db, schedule) if schedule else _fallback_schedule(target)
    return {
        "date": target.isoformat(), "weekday": target.weekday(), "weekday_label": WEEKDAY_LABELS[target.weekday()],
        "is_working_day": is_working, "status": status, "label": labels[status],
        "holiday_name": exception["holiday_name"] if exception else None,
        "note": exception["note"] if exception else None,
        "config": config,
    }


def _fallback_schedule(target: date) -> dict:
    return {
        "effective_from": target.isoformat(),
        **{field: 1 for field in WEEKDAY_FIELDS},
        "start_time": "08:00", "end_time": "17:00", "late_allowed_minutes": 5,
        "early_leave_allowed_minutes": 10, "checkout_cutoff_time": "23:59", "updated_at": None,
    }


def _config_dict(db, schedule) -> dict:
    config = dict(schedule)
    # The initial row preserves the legacy system settings until an admin saves
    # the first dedicated work schedule. This keeps existing installations stable.
    if config.get("effective_from") != "1970-01-01":
        return config
    values = {
        row["key"]: row["value"]
        for row in db.execute(
            """
            SELECT key, value FROM settings
            WHERE key IN ('work_start_time', 'work_end_time', 'late_grace_minutes',
                          'early_leave_grace_minutes', 'missing_checkout_cutoff_time')
            """
        ).fetchall()
    }
    config.update({
        "start_time": values.get("work_start_time", config["start_time"]),
        "end_time": values.get("work_end_time", config["end_time"]),
        "late_allowed_minutes": int(values.get("late_grace_minutes", config["late_allowed_minutes"])),
        "early_leave_allowed_minutes": int(values.get("early_leave_grace_minutes", config["early_leave_allowed_minutes"])),
        "checkout_cutoff_time": values.get("missing_checkout_cutoff_time", config["checkout_cutoff_time"]),
    })
    return config

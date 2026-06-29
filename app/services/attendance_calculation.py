from datetime import datetime, timedelta


def parse_log_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def ceil_minutes(delta: timedelta) -> int:
    seconds = max(0, int(delta.total_seconds()))
    return (seconds + 59) // 60


def date_text(value: datetime) -> str:
    return value.date().isoformat()


def combine_date_time(date_text_value: str, value) -> datetime:
    return datetime.combine(datetime.fromisoformat(date_text_value).date(), value)


def time_text(value: datetime | None) -> str:
    return value.strftime("%H:%M") if value else "--:--"


def duration_text(minutes: int) -> str:
    if minutes <= 0:
        return "0p"
    hours = minutes // 60
    rest = minutes % 60
    if not hours:
        return f"{rest}p"
    return f"{hours}h {rest}p" if rest else f"{hours}h"


def iso_text(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") if value else None


def summarize_day_logs(rows) -> dict:
    first_check_in = None
    last_check_out = None
    open_check_in = None
    pending_out_at = None
    last_action = None
    last_log_at = None
    total_minutes = 0
    sessions = []
    outside_periods = []
    logs = []

    for row in rows:
        created_at = parse_log_time(row["created_at"])
        if not created_at:
            continue
        action = row["action"]
        logs.append(
            {
                "action": action,
                "created_at": created_at.isoformat(timespec="seconds"),
                "note": row["note"] if "note" in row.keys() else None,
            }
        )
        last_action = action
        last_log_at = created_at
        if action == "check_in":
            if first_check_in is None or created_at < first_check_in:
                first_check_in = created_at
            if pending_out_at and created_at >= pending_out_at:
                outside_minutes = ceil_minutes(created_at - pending_out_at)
                outside_periods.append(
                    {
                        "start_at": pending_out_at.isoformat(timespec="seconds"),
                        "end_at": created_at.isoformat(timespec="seconds"),
                        "minutes": max(0, outside_minutes),
                    }
                )
                pending_out_at = None
            open_check_in = created_at
            continue
        if action == "check_out":
            if last_check_out is None or created_at > last_check_out:
                last_check_out = created_at
            if open_check_in and created_at >= open_check_in:
                session_minutes = int((created_at - open_check_in).total_seconds() // 60)
                total_minutes += session_minutes
                sessions.append(
                    {
                        "start_at": open_check_in.isoformat(timespec="seconds"),
                        "end_at": created_at.isoformat(timespec="seconds"),
                        "minutes": max(0, session_minutes),
                    }
                )
                open_check_in = None
            pending_out_at = created_at

    current_out_since_at = pending_out_at if last_action == "check_out" else None
    outside_minutes = sum(item["minutes"] for item in outside_periods)

    return {
        "first_check_in_at": iso_text(first_check_in),
        "last_check_out_at": iso_text(last_check_out),
        "last_action": last_action,
        "last_log_at": iso_text(last_log_at),
        "open_check_in_at": iso_text(open_check_in),
        "current_out_since_at": iso_text(current_out_since_at),
        "presence_status": "in_lab" if last_action == "check_in" else ("out_of_lab" if last_action == "check_out" else None),
        "total_minutes": max(0, total_minutes),
        "outside_count": len(outside_periods),
        "outside_minutes": max(0, outside_minutes),
        "sessions": sessions,
        "outside_periods": outside_periods,
        "logs": logs,
    }

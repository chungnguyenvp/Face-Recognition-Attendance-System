def get_schedule_for_date(db, target_date: str):
    return db.execute(
        """
        SELECT * FROM work_schedule_settings
        WHERE effective_from <= ?
        ORDER BY effective_from DESC, id DESC
        LIMIT 1
        """,
        (target_date,),
    ).fetchone()


def get_latest_schedule(db):
    return db.execute(
        "SELECT * FROM work_schedule_settings ORDER BY effective_from DESC, id DESC LIMIT 1"
    ).fetchone()


def upsert_schedule(db, values: dict) -> None:
    columns = (
        "effective_from, monday_enabled, tuesday_enabled, wednesday_enabled, "
        "thursday_enabled, friday_enabled, saturday_enabled, sunday_enabled, "
        "start_time, end_time, late_allowed_minutes, early_leave_allowed_minutes, "
        "checkout_cutoff_time, updated_at"
    )
    db.execute(
        f"""
        INSERT INTO work_schedule_settings({columns})
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(effective_from) DO UPDATE SET
            monday_enabled=excluded.monday_enabled,
            tuesday_enabled=excluded.tuesday_enabled,
            wednesday_enabled=excluded.wednesday_enabled,
            thursday_enabled=excluded.thursday_enabled,
            friday_enabled=excluded.friday_enabled,
            saturday_enabled=excluded.saturday_enabled,
            sunday_enabled=excluded.sunday_enabled,
            start_time=excluded.start_time,
            end_time=excluded.end_time,
            late_allowed_minutes=excluded.late_allowed_minutes,
            early_leave_allowed_minutes=excluded.early_leave_allowed_minutes,
            checkout_cutoff_time=excluded.checkout_cutoff_time,
            updated_at=excluded.updated_at
        """,
        (
            values["effective_from"], values["monday_enabled"], values["tuesday_enabled"],
            values["wednesday_enabled"], values["thursday_enabled"], values["friday_enabled"],
            values["saturday_enabled"], values["sunday_enabled"], values["start_time"],
            values["end_time"], values["late_allowed_minutes"],
            values["early_leave_allowed_minutes"], values["checkout_cutoff_time"], values["updated_at"],
        ),
    )


def get_exception_by_id(db, exception_id: int):
    return db.execute("SELECT * FROM work_calendar_exceptions WHERE id=?", (exception_id,)).fetchone()


def get_exception_for_date(db, target_date: str):
    return db.execute(
        "SELECT * FROM work_calendar_exceptions WHERE exception_date=?",
        (target_date,),
    ).fetchone()


def list_exceptions(db, date_from: str | None = None, date_to: str | None = None):
    clauses, params = ["1=1"], []
    if date_from:
        clauses.append("exception_date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("exception_date <= ?")
        params.append(date_to)
    return db.execute(
        f"SELECT * FROM work_calendar_exceptions WHERE {' AND '.join(clauses)} ORDER BY exception_date DESC, id DESC",
        params,
    ).fetchall()


def upsert_exception(db, exception_id: int | None, values: dict) -> int:
    if exception_id is None:
        cursor = db.execute(
            """
            INSERT INTO work_calendar_exceptions(exception_date, exception_type, holiday_name, note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                values["exception_date"], values["exception_type"], values["holiday_name"],
                values.get("note"), values["created_at"], values["updated_at"],
            ),
        )
        return cursor.lastrowid
    db.execute(
        """
        UPDATE work_calendar_exceptions
        SET exception_date=?, exception_type=?, holiday_name=?, note=?, updated_at=?
        WHERE id=?
        """,
        (
            values["exception_date"], values["exception_type"], values["holiday_name"],
            values.get("note"), values["updated_at"], exception_id,
        ),
    )
    return exception_id


def delete_exception(db, exception_id: int) -> bool:
    return db.execute("DELETE FROM work_calendar_exceptions WHERE id=?", (exception_id,)).rowcount > 0

from app.repositories.query_filters import append_attendance_date_filters


def get_student_attendance_config(db, student_id: int):
    return db.execute(
        "SELECT work_start_time, work_end_time FROM student_attendance_settings WHERE student_id=?",
        (student_id,),
    ).fetchone()


def list_attendance_day_logs(db, student_id: int, attendance_date: str):
    return db.execute(
        """
        SELECT action, created_at, note FROM access_logs
        WHERE student_id=?
            AND result='success'
            AND action IN ('check_in', 'check_out')
            AND date(created_at)=date(?)
        ORDER BY created_at ASC, id ASC
        """,
        (student_id, attendance_date),
    ).fetchall()


def get_attendance_record_by_id(db, record_id: int):
    return db.execute("SELECT * FROM attendance_records WHERE id=?", (record_id,)).fetchone()


def get_attendance_record_by_student_date(db, student_id: int, attendance_date: str):
    return db.execute(
        "SELECT * FROM attendance_records WHERE student_id=? AND attendance_date=?",
        (student_id, attendance_date),
    ).fetchone()


def list_student_attendance_dates(db, student_id: int):
    return db.execute(
        """
        SELECT DISTINCT date_text FROM (
            SELECT date(created_at) date_text FROM access_logs WHERE student_id=?
            UNION
            SELECT attendance_date date_text FROM attendance_records WHERE student_id=?
            UNION
            SELECT date('now','localtime') date_text
        )
        WHERE date_text IS NOT NULL
        ORDER BY date_text
        """,
        (student_id, student_id),
    ).fetchall()


def clear_missing_checkout_resolution(db, record_id: int) -> None:
    db.execute(
        """
        UPDATE attendance_records
        SET missing_checkout_resolution=NULL,
            resolution_reason=NULL,
            resolution_checkout_at=NULL,
            force_zero_minutes=0
        WHERE id=?
        """,
        (record_id,),
    )


def set_missing_checkout_keep_zero_resolution(
    db,
    record_id: int,
    note: str,
    resolution_type: str,
    resolution_reason: str,
    updated_at: str,
) -> None:
    db.execute(
        """
        UPDATE attendance_records
        SET status='missing_checkout', total_minutes=0, missing_checkout=1, note=?,
            missing_checkout_resolution=?, resolution_reason=?,
            resolution_checkout_at=NULL, force_zero_minutes=1, updated_at=?
        WHERE id=?
        """,
        (note, resolution_type, resolution_reason, updated_at, record_id),
    )


def set_missing_checkout_resolution(
    db,
    record_id: int,
    resolution_type: str,
    resolution_reason: str,
    resolution_checkout_at: str,
    updated_at: str,
) -> None:
    db.execute(
        """
        UPDATE attendance_records
        SET missing_checkout_resolution=?, resolution_reason=?,
            resolution_checkout_at=?, force_zero_minutes=0, updated_at=?
        WHERE id=?
        """,
        (resolution_type, resolution_reason, resolution_checkout_at, updated_at, record_id),
    )


def set_auto_work_end_missing_checkout_resolution(
    db,
    student_id: int,
    attendance_date: str,
    resolution_reason: str,
    resolution_checkout_at: str,
    note: str,
    updated_at: str,
) -> None:
    db.execute(
        """
        UPDATE attendance_records
        SET missing_checkout_resolution='auto_work_end',
            resolution_reason=?,
            resolution_checkout_at=?,
            force_zero_minutes=0,
            missing_checkout=0,
            note=?,
            updated_at=?
        WHERE student_id=? AND attendance_date=?
        """,
        (
            resolution_reason,
            resolution_checkout_at,
            note,
            updated_at,
            student_id,
            attendance_date,
        ),
    )


def update_attendance_record_summary(
    db,
    record_id: int,
    student_code: str,
    full_name: str,
    first_check_in_at: str | None,
    last_check_out_at: str | None,
    status: str,
    late_minutes: int,
    early_leave_minutes: int,
    total_minutes: int,
    missing_checkout: bool,
    note: str | None,
    updated_at: str,
) -> None:
    db.execute(
        """
        UPDATE attendance_records
        SET student_code=?, full_name=?, first_check_in_at=?, last_check_out_at=?,
            status=?, late_minutes=?, early_leave_minutes=?, total_minutes=?,
            missing_checkout=?, note=?, updated_at=?
        WHERE id=?
        """,
        (
            student_code,
            full_name,
            first_check_in_at,
            last_check_out_at,
            status,
            late_minutes,
            early_leave_minutes,
            total_minutes,
            1 if missing_checkout else 0,
            note,
            updated_at,
            record_id,
        ),
    )


def create_attendance_record(
    db,
    student_id: int,
    student_code: str,
    full_name: str,
    attendance_date: str,
    first_check_in_at: str | None,
    last_check_out_at: str | None,
    status: str,
    late_minutes: int,
    early_leave_minutes: int,
    total_minutes: int,
    missing_checkout: bool,
    note: str | None,
    created_at: str,
    updated_at: str,
) -> None:
    db.execute(
        """
        INSERT INTO attendance_records(
            student_id, student_code, full_name, attendance_date,
            first_check_in_at, last_check_out_at, status, late_minutes,
            early_leave_minutes, total_minutes, missing_checkout, note, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
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
            1 if missing_checkout else 0,
            note,
            created_at,
            updated_at,
        ),
    )


def list_attendance_records(
    db,
    limit: int,
    date_from: str | None = None,
    date_to: str | None = None,
    status: str | None = None,
    q: str | None = None,
):
    clauses = ["1=1"]
    params = []
    append_attendance_date_filters(clauses, params, date_from, date_to)
    if status:
        clauses.append("status=?")
        params.append(status)
    if q:
        clauses.append("(student_code LIKE ? OR full_name LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like])
    safe_limit = max(1, min(int(limit), 1000))
    return db.execute(
        f"""
        SELECT * FROM attendance_records
        WHERE {' AND '.join(clauses)}
        ORDER BY attendance_date DESC, full_name ASC, id ASC
        LIMIT ?
        """,
        (*params, safe_limit),
    ).fetchall()

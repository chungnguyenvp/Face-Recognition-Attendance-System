from app.repositories.query_filters import append_created_date_filters


def list_access_logs(
    db,
    limit: int,
    date_from: str | None = None,
    date_to: str | None = None,
    action: str | None = None,
    result: str | None = None,
    q: str | None = None,
):
    clauses = ["1=1"]
    params = []
    append_created_date_filters(clauses, params, date_from, date_to)
    if action:
        clauses.append("action=?")
        params.append(action)
    if result:
        clauses.append("result=?")
        params.append(result)
    if q:
        clauses.append("(student_code LIKE ? OR full_name LIKE ? OR note LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])
    safe_limit = max(1, min(int(limit), 500))
    return db.execute(
        f"SELECT * FROM access_logs WHERE {' AND '.join(clauses)} ORDER BY id DESC LIMIT ?",
        (*params, safe_limit),
    ).fetchall()


def get_access_log_delete_summary(db, log_id: int):
    return db.execute(
        """
        SELECT id, student_id, student_code, full_name, action, result, date(created_at) AS attendance_date
        FROM access_logs
        WHERE id=?
        """,
        (log_id,),
    ).fetchone()


def get_last_success_created_at(db, student_id: int, action: str):
    return db.execute(
        """
        SELECT created_at FROM access_logs
        WHERE student_id=? AND action=? AND result='success'
        ORDER BY id DESC
        LIMIT 1
        """,
        (student_id, action),
    ).fetchone()


def get_current_presence_action(db, student_id: int):
    return db.execute(
        """
        SELECT action, created_at FROM access_logs
        WHERE student_id=? AND result='success' AND action IN ('check_in', 'check_out')
        ORDER BY id DESC
        LIMIT 1
        """,
        (student_id,),
    ).fetchone()


def list_successful_check_events_until(db, created_before: str):
    return db.execute(
        """
        SELECT * FROM access_logs
        WHERE student_id IS NOT NULL
            AND result='success'
            AND action IN ('check_in', 'check_out')
            AND created_at <= ?
        ORDER BY created_at ASC, id ASC
        """,
        (created_before,),
    ).fetchall()


def get_last_success_check_event(db, student_id: int):
    return db.execute(
        """
        SELECT * FROM access_logs
        WHERE student_id=? AND result='success' AND action IN ('check_in', 'check_out')
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (student_id,),
    ).fetchone()


def delete_successful_check_out_at(db, student_id: int, created_at: str) -> None:
    db.execute(
        """
        DELETE FROM access_logs
        WHERE student_id=? AND action='check_out' AND result='success' AND created_at=?
        """,
        (student_id, created_at),
    )


def create_access_log(
    db,
    student_id: int | None,
    student_code: str,
    full_name: str,
    action: str,
    result: str,
    confidence,
    note: str | None,
    evidence_image_path: str | None,
    created_at: str,
) -> None:
    db.execute(
        """
        INSERT INTO access_logs(student_id, student_code, full_name, action, result, confidence, note, evidence_image_path, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            student_id,
            student_code,
            full_name,
            action,
            result,
            confidence,
            note,
            evidence_image_path,
            created_at,
        ),
    )


def delete_access_log(db, log_id: int) -> None:
    db.execute("DELETE FROM access_logs WHERE id=?", (log_id,))

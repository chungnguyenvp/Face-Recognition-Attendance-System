from app.repositories.query_filters import append_attendance_date_filters, append_created_date_filters


def get_student_profile(db, student_id: int):
    return db.execute(
        """
        SELECT s.*, COUNT(f.id) AS face_count
        FROM students s
        LEFT JOIN student_faces f ON f.student_id = s.id
        WHERE s.id = ?
        GROUP BY s.id
        """,
        (student_id,),
    ).fetchone()


def list_registered_faces(db, student_id: int):
    return db.execute(
        """
        SELECT id, image_path, created_at
        FROM student_faces
        WHERE student_id = ?
        ORDER BY id DESC
        """,
        (student_id,),
    ).fetchall()


def list_access_logs(
    db,
    student_id: int,
    limit: int,
    date_from: str | None = None,
    date_to: str | None = None,
    action: str | None = None,
    result: str | None = None,
):
    clauses = ["student_id=?"]
    params = [student_id]
    append_created_date_filters(clauses, params, date_from, date_to)
    if action:
        clauses.append("action=?")
        params.append(action)
    if result:
        clauses.append("result=?")
        params.append(result)
    safe_limit = max(1, min(int(limit), 300))
    return db.execute(
        f"""
        SELECT * FROM access_logs
        WHERE {' AND '.join(clauses)}
        ORDER BY id DESC
        LIMIT ?
        """,
        (*params, safe_limit),
    ).fetchall()


def list_attendance_records(
    db,
    student_id: int,
    limit: int,
    date_from: str | None = None,
    date_to: str | None = None,
    status: str | None = None,
):
    clauses = ["student_id=?"]
    params = [student_id]
    append_attendance_date_filters(clauses, params, date_from, date_to)
    if status:
        clauses.append("status=?")
        params.append(status)
    safe_limit = max(1, min(int(limit), 300))
    return db.execute(
        f"""
        SELECT * FROM attendance_records
        WHERE {' AND '.join(clauses)}
        ORDER BY attendance_date DESC, id DESC
        LIMIT ?
        """,
        (*params, safe_limit),
    ).fetchall()

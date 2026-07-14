MAX_EXPORT_ROWS = 50_000


def list_attendance_export_rows(
    db,
    date_from: str,
    date_to: str,
    status: str | None = None,
    q: str | None = None,
    class_name: str | None = None,
):
    clauses = [
        "date(ar.attendance_date) >= date(?)",
        "date(ar.attendance_date) <= date(?)",
    ]
    params: list[object] = [date_from, date_to]
    if status:
        clauses.append("ar.status=?")
        params.append(status)
    if q:
        clauses.append("(ar.student_code LIKE ? OR ar.full_name LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like])
    if class_name:
        clauses.append("COALESCE(s.class_name, '') LIKE ?")
        params.append(f"%{class_name}%")

    return db.execute(
        f"""
        SELECT
            ar.id,
            ar.student_id,
            ar.student_code,
            ar.full_name,
            COALESCE(s.class_name, '') AS class_name,
            ar.attendance_date,
            ar.first_check_in_at,
            ar.last_check_out_at,
            ar.status,
            ar.late_minutes,
            ar.early_leave_minutes,
            ar.total_minutes,
            ar.missing_checkout,
            ar.note
        FROM attendance_records ar
        LEFT JOIN students s ON s.id = ar.student_id
        WHERE {' AND '.join(clauses)}
        ORDER BY ar.attendance_date ASC, ar.full_name ASC, ar.id ASC
        LIMIT ?
        """,
        (*params, MAX_EXPORT_ROWS + 1),
    ).fetchall()

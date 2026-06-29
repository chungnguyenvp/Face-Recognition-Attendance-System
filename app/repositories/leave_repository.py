from __future__ import annotations


def create_leave_request(db, student_id: int, leave_type: str, start_date: str, end_date: str, reason: str, created_at: str) -> int:
    cursor = db.execute(
        """
        INSERT INTO leave_requests(student_id, leave_type, start_date, end_date, reason, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
        """,
        (student_id, leave_type, start_date, end_date, reason, created_at, created_at),
    )
    return cursor.lastrowid


def get_leave_request_by_id(db, leave_id: int):
    return db.execute(
        """
        SELECT lr.*, s.student_code, s.full_name, u.username AS reviewer_username
        FROM leave_requests lr
        JOIN students s ON s.id = lr.student_id
        LEFT JOIN users u ON u.id = lr.reviewer_id
        WHERE lr.id=?
        """,
        (leave_id,),
    ).fetchone()


def list_leave_requests_by_student(db, student_id: int, limit: int):
    safe_limit = max(1, min(int(limit), 300))
    return db.execute(
        """
        SELECT lr.*, s.student_code, s.full_name, u.username AS reviewer_username
        FROM leave_requests lr JOIN students s ON s.id = lr.student_id
        LEFT JOIN users u ON u.id = lr.reviewer_id
        WHERE lr.student_id=? ORDER BY lr.created_at DESC, lr.id DESC LIMIT ?
        """,
        (student_id, safe_limit),
    ).fetchall()


def list_leave_requests_for_staff(db, limit: int, status: str | None = None, leave_type: str | None = None,
                                  date_from: str | None = None, date_to: str | None = None, q: str | None = None):
    clauses, params = ["1=1"], []
    if status:
        clauses.append("lr.status=?")
        params.append(status)
    if leave_type:
        clauses.append("lr.leave_type=?")
        params.append(leave_type)
    if date_from:
        clauses.append("lr.end_date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("lr.start_date <= ?")
        params.append(date_to)
    if q:
        clauses.append("(s.student_code LIKE ? OR s.full_name LIKE ?)")
        params.extend([f"%{q.strip()}%", f"%{q.strip()}%"])
    safe_limit = max(1, min(int(limit), 500))
    return db.execute(
        f"""
        SELECT lr.*, s.student_code, s.full_name, u.username AS reviewer_username
        FROM leave_requests lr JOIN students s ON s.id = lr.student_id
        LEFT JOIN users u ON u.id = lr.reviewer_id
        WHERE {' AND '.join(clauses)}
        ORDER BY CASE lr.status WHEN 'pending' THEN 0 ELSE 1 END, lr.start_date DESC, lr.id DESC
        LIMIT ?
        """,
        (*params, safe_limit),
    ).fetchall()


def has_overlapping_leave_request(db, student_id: int, start_date: str, end_date: str) -> bool:
    row = db.execute(
        """
        SELECT 1 FROM leave_requests
        WHERE student_id=? AND status IN ('pending', 'approved')
          AND start_date <= ? AND end_date >= ? LIMIT 1
        """,
        (student_id, end_date, start_date),
    ).fetchone()
    return row is not None


def update_pending_review(db, leave_id: int, status: str, reviewer_id: int, reviewer_note: str | None, now_text: str) -> bool:
    timestamp_column = "approved_at" if status == "approved" else "rejected_at"
    cursor = db.execute(
        f"""UPDATE leave_requests SET status=?, reviewer_id=?, reviewer_note=?, {timestamp_column}=?, updated_at=?
        WHERE id=? AND status='pending'""",
        (status, reviewer_id, reviewer_note, now_text, now_text, leave_id),
    )
    return cursor.rowcount == 1


def cancel_pending_leave_request(db, leave_id: int, now_text: str) -> bool:
    cursor = db.execute(
        "UPDATE leave_requests SET status='cancelled', cancelled_at=?, updated_at=? WHERE id=? AND status='pending'",
        (now_text, now_text, leave_id),
    )
    return cursor.rowcount == 1


def revoke_approved_leave_request(db, leave_id: int, reviewer_id: int, reviewer_note: str, now_text: str) -> bool:
    cursor = db.execute(
        """UPDATE leave_requests SET status='revoked', reviewer_id=?, reviewer_note=?, revoked_at=?, updated_at=?
        WHERE id=? AND status='approved'""",
        (reviewer_id, reviewer_note, now_text, now_text, leave_id),
    )
    return cursor.rowcount == 1


def find_leave_status_for_student_on_date(db, student_id: int, target_date: str) -> str | None:
    row = db.execute(
        """
        SELECT status FROM leave_requests
        WHERE student_id=? AND status IN ('approved', 'pending') AND start_date <= ? AND end_date >= ?
        ORDER BY CASE status WHEN 'approved' THEN 0 ELSE 1 END, created_at DESC LIMIT 1
        """,
        (student_id, target_date, target_date),
    ).fetchone()
    return row["status"] if row else None


def student_has_leave_history(db, student_id: int) -> bool:
    return db.execute("SELECT 1 FROM leave_requests WHERE student_id=? LIMIT 1", (student_id,)).fetchone() is not None

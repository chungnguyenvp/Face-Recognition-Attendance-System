from __future__ import annotations


IMAGE_COLUMNS = (
    "front_image_path",
    "left_image_path",
    "right_image_path",
    "up_image_path",
    "down_image_path",
)


def create_request(
    db,
    student_id: int,
    request_type: str,
    face_count_at_submit: int,
    planned_remove_count: int,
    storage_key: str,
    image_paths: dict[str, str],
    note: str | None,
    now_text: str,
) -> int:
    cursor = db.execute(
        """
        INSERT INTO face_registration_requests(
            student_id, status, request_type, face_count_at_submit, planned_remove_count,
            storage_key, front_image_path, left_image_path,
            right_image_path, up_image_path, down_image_path, note, created_at, updated_at
        ) VALUES (?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            student_id,
            request_type,
            face_count_at_submit,
            planned_remove_count,
            storage_key,
            image_paths["front"],
            image_paths["left"],
            image_paths["right"],
            image_paths["up"],
            image_paths["down"],
            note,
            now_text,
            now_text,
        ),
    )
    return cursor.lastrowid


def get_request_by_id(db, request_id: int):
    return db.execute(
        """
        SELECT r.*, s.student_code, s.full_name, s.class_name,
               u.username AS reviewer_username
        FROM face_registration_requests r
        JOIN students s ON s.id = r.student_id
        LEFT JOIN users u ON u.id = r.reviewed_by
        WHERE r.id=?
        """,
        (request_id,),
    ).fetchone()


def get_latest_request_by_student(db, student_id: int):
    return db.execute(
        """
        SELECT r.*, u.username AS reviewer_username
        FROM face_registration_requests r
        LEFT JOIN users u ON u.id = r.reviewed_by
        WHERE r.student_id=?
        ORDER BY r.created_at DESC, r.id DESC
        LIMIT 1
        """,
        (student_id,),
    ).fetchone()


def get_pending_request_by_student(db, student_id: int):
    return db.execute(
        "SELECT * FROM face_registration_requests WHERE student_id=? AND status='pending' LIMIT 1",
        (student_id,),
    ).fetchone()


def list_requests_for_staff(db, limit: int, status: str | None = None, q: str | None = None):
    clauses, params = ["1=1"], []
    if status:
        clauses.append("r.status=?")
        params.append(status)
    if q and q.strip():
        keyword = f"%{q.strip()}%"
        clauses.append("(s.student_code LIKE ? OR s.full_name LIKE ? OR s.class_name LIKE ?)")
        params.extend([keyword, keyword, keyword])
    safe_limit = max(1, min(int(limit), 500))
    return db.execute(
        f"""
        SELECT r.*, s.student_code, s.full_name, s.class_name,
               u.username AS reviewer_username
        FROM face_registration_requests r
        JOIN students s ON s.id = r.student_id
        LEFT JOIN users u ON u.id = r.reviewed_by
        WHERE {' AND '.join(clauses)}
        ORDER BY CASE r.status WHEN 'pending' THEN 0 ELSE 1 END, r.created_at DESC, r.id DESC
        LIMIT ?
        """,
        (*params, safe_limit),
    ).fetchall()


def mark_approved(db, request_id: int, reviewer_id: int, now_text: str) -> bool:
    cursor = db.execute(
        """
        UPDATE face_registration_requests
        SET status='approved', reviewed_by=?, reviewed_at=?, updated_at=?
        WHERE id=? AND status='pending'
        """,
        (reviewer_id, now_text, now_text, request_id),
    )
    return cursor.rowcount == 1


def mark_rejected(db, request_id: int, reviewer_id: int, reason: str, now_text: str) -> bool:
    cursor = db.execute(
        """
        UPDATE face_registration_requests
        SET status='rejected', reject_reason=?, reviewed_by=?, reviewed_at=?, updated_at=?
        WHERE id=? AND status='pending'
        """,
        (reason, reviewer_id, now_text, now_text, request_id),
    )
    return cursor.rowcount == 1


def cancel_pending_request(db, request_id: int, student_id: int, now_text: str) -> bool:
    cursor = db.execute(
        """
        UPDATE face_registration_requests
        SET status='cancelled', updated_at=?
        WHERE id=? AND student_id=? AND status='pending'
        """,
        (now_text, request_id, student_id),
    )
    return cursor.rowcount == 1

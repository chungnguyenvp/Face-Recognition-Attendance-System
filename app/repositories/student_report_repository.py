from __future__ import annotations


def list_active_lab_managers(db):
    return db.execute(
        "SELECT id, username FROM users WHERE role='lab_manager' AND status='active' ORDER BY username COLLATE NOCASE"
    ).fetchall()


def create_report(db, student_id: int, reviewer_id: int, title: str, report_type: str, created_at: str) -> int:
    cursor = db.execute(
        """INSERT INTO student_reports(student_id, reviewer_id, title, report_type, status, current_version, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'submitted', 1, ?, ?)""",
        (student_id, reviewer_id, title, report_type, created_at, created_at),
    )
    return cursor.lastrowid


def create_version(db, report_id: int, version_no: int, description: str | None, external_link: str | None,
                   original_filename: str | None, storage_path: str | None, file_size: int | None,
                   media_type: str | None, submitted_by: int, submitted_at: str) -> int:
    cursor = db.execute(
        """INSERT INTO student_report_versions(
            report_id, version_no, description, external_link, original_filename, storage_path, file_size, media_type,
            submitted_by, submitted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (report_id, version_no, description, external_link, original_filename, storage_path, file_size, media_type, submitted_by, submitted_at),
    )
    return cursor.lastrowid


def get_report(db, report_id: int):
    return db.execute(
        """SELECT r.*, s.student_code, s.full_name, reviewer.username AS reviewer_username,
                  v.id AS current_version_id, v.description AS current_description, v.external_link AS current_external_link,
                  v.original_filename AS current_original_filename, v.storage_path AS current_storage_path,
                  v.file_size AS current_file_size, v.media_type AS current_media_type,
                  v.submitted_at AS current_submitted_at, v.viewed_at AS current_viewed_at
           FROM student_reports r
           JOIN students s ON s.id=r.student_id
           JOIN users reviewer ON reviewer.id=r.reviewer_id
           LEFT JOIN student_report_versions v ON v.report_id=r.id AND v.version_no=r.current_version
           WHERE r.id=?""",
        (report_id,),
    ).fetchone()


def get_report_for_student(db, report_id: int, student_id: int):
    row = get_report(db, report_id)
    return row if row and row["student_id"] == student_id else None


def list_reports_for_student(db, student_id: int, limit: int):
    return db.execute(
        """SELECT r.*, reviewer.username AS reviewer_username, v.submitted_at AS current_submitted_at,
                  v.original_filename AS current_original_filename, v.file_size AS current_file_size, v.viewed_at AS current_viewed_at,
                  (SELECT COUNT(*) FROM student_report_feedbacks f WHERE f.report_id=r.id) AS feedback_count
           FROM student_reports r
           JOIN users reviewer ON reviewer.id=r.reviewer_id
           JOIN student_report_versions v ON v.report_id=r.id AND v.version_no=r.current_version
           WHERE r.student_id=? ORDER BY r.updated_at DESC, r.id DESC LIMIT ?""",
        (student_id, limit),
    ).fetchall()


def list_reports_for_staff(db, reviewer_id: int | None, limit: int, status: str | None, report_type: str | None, q: str | None):
    clauses, params = ["1=1"], []
    if reviewer_id is not None:
        clauses.append("r.reviewer_id=?")
        params.append(reviewer_id)
    if status:
        clauses.append("r.status=?")
        params.append(status)
    if report_type:
        clauses.append("r.report_type=?")
        params.append(report_type)
    if q and q.strip():
        clauses.append("(s.student_code LIKE ? OR s.full_name LIKE ? OR r.title LIKE ?)")
        needle = f"%{q.strip()}%"
        params.extend([needle, needle, needle])
    return db.execute(
        f"""SELECT r.*, s.student_code, s.full_name, reviewer.username AS reviewer_username,
                   v.submitted_at AS current_submitted_at, v.original_filename AS current_original_filename,
                   v.viewed_at AS current_viewed_at,
                   (SELECT COUNT(*) FROM student_report_feedbacks f WHERE f.report_id=r.id) AS feedback_count
            FROM student_reports r
            JOIN students s ON s.id=r.student_id
            JOIN users reviewer ON reviewer.id=r.reviewer_id
            JOIN student_report_versions v ON v.report_id=r.id AND v.version_no=r.current_version
            WHERE {' AND '.join(clauses)}
            ORDER BY CASE WHEN v.viewed_at IS NULL THEN 0 ELSE 1 END, r.updated_at DESC, r.id DESC LIMIT ?""",
        (*params, limit),
    ).fetchall()


def list_versions(db, report_id: int):
    return db.execute(
        """SELECT v.*, u.username AS submitted_by_username
           FROM student_report_versions v JOIN users u ON u.id=v.submitted_by
           WHERE v.report_id=? ORDER BY v.version_no DESC""",
        (report_id,),
    ).fetchall()


def get_version(db, report_id: int, version_no: int):
    return db.execute(
        "SELECT * FROM student_report_versions WHERE report_id=? AND version_no=?",
        (report_id, version_no),
    ).fetchone()


def list_feedbacks(db, report_id: int):
    return db.execute(
        """SELECT f.*, u.username AS reviewer_username, v.version_no
           FROM student_report_feedbacks f
           JOIN users u ON u.id=f.reviewer_id
           JOIN student_report_versions v ON v.id=f.version_id
           WHERE f.report_id=? ORDER BY f.created_at ASC, f.id ASC""",
        (report_id,),
    ).fetchall()


def update_for_resubmission(db, report_id: int, version_no: int, updated_at: str) -> bool:
    cursor = db.execute(
        """UPDATE student_reports SET status='submitted', current_version=?, updated_at=?
           WHERE id=? AND status='revision_requested'""",
        (version_no, updated_at, report_id),
    )
    return cursor.rowcount == 1


def mark_current_version_viewed(db, report_id: int, viewed_at: str) -> None:
    db.execute(
        """UPDATE student_report_versions SET viewed_at=COALESCE(viewed_at, ?)
           WHERE report_id=? AND version_no=(SELECT current_version FROM student_reports WHERE id=?)""",
        (viewed_at, report_id, report_id),
    )


def create_feedback(db, report_id: int, version_id: int, reviewer_id: int, status: str, comment: str | None, created_at: str) -> int:
    cursor = db.execute(
        """INSERT INTO student_report_feedbacks(report_id, version_id, reviewer_id, status, comment, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (report_id, version_id, reviewer_id, status, comment, created_at),
    )
    return cursor.lastrowid


def update_review_status(db, report_id: int, status: str, updated_at: str) -> bool:
    cursor = db.execute(
        "UPDATE student_reports SET status=?, updated_at=? WHERE id=? AND status='submitted'",
        (status, updated_at, report_id),
    )
    return cursor.rowcount == 1

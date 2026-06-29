def list_active_students(db, q: str, default_start: str, default_end: str):
    if q:
        return db.execute(
            """
            SELECT s.*, COUNT(f.id) AS face_count,
                COALESCE(a.work_start_time, ?) AS work_start_time,
                COALESCE(a.work_end_time, ?) AS work_end_time
            FROM students s
            LEFT JOIN student_faces f ON s.id = f.student_id
            LEFT JOIN student_attendance_settings a ON a.student_id = s.id
            WHERE (s.student_code LIKE ? OR s.full_name LIKE ?)
              AND s.status='active'
            GROUP BY s.id
            ORDER BY s.id DESC
            """,
            (default_start, default_end, f"%{q}%", f"%{q}%"),
        ).fetchall()

    return db.execute(
        """
        SELECT s.*, COUNT(f.id) AS face_count,
            COALESCE(a.work_start_time, ?) AS work_start_time,
            COALESCE(a.work_end_time, ?) AS work_end_time
        FROM students s
        LEFT JOIN student_faces f ON s.id = f.student_id
        LEFT JOIN student_attendance_settings a ON a.student_id = s.id
        WHERE s.status='active'
        GROUP BY s.id
        ORDER BY s.id DESC
        """,
        (default_start, default_end),
    ).fetchall()


def create_student(db, student_code: str, full_name: str, class_name: str, status: str, created_at: str) -> int:
    cur = db.execute(
        """
        INSERT INTO students(student_code, full_name, class_name, status, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (student_code, full_name, class_name, status, created_at),
    )
    return cur.lastrowid


def get_student_by_id(db, student_id: int):
    return db.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()


def update_student_profile(db, student_id: int, student_code: str, full_name: str, class_name: str, status: str) -> None:
    db.execute(
        """
        UPDATE students SET student_code=?, full_name=?, class_name=?, status=? WHERE id=?
        """,
        (student_code, full_name, class_name, status, student_id),
    )


def get_student_identity(db, student_id: int):
    return db.execute(
        "SELECT id, student_code, full_name FROM students WHERE id = ?",
        (student_id,),
    ).fetchone()


def list_active_student_identities(db):
    return db.execute(
        "SELECT id, student_code, full_name FROM students WHERE status='active'"
    ).fetchall()


def get_student_work_time(db, student_id: int):
    return db.execute(
        "SELECT work_start_time, work_end_time FROM student_attendance_settings WHERE student_id=?",
        (student_id,),
    ).fetchone()


def upsert_student_work_time(db, student_id: int, work_start_time: str, work_end_time: str, updated_at: str) -> None:
    db.execute(
        """
        INSERT INTO student_attendance_settings(student_id, work_start_time, work_end_time, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(student_id) DO UPDATE SET
            work_start_time=excluded.work_start_time,
            work_end_time=excluded.work_end_time,
            updated_at=excluded.updated_at
        """,
        (student_id, work_start_time, work_end_time, updated_at),
    )


def delete_student_work_time(db, student_id: int) -> None:
    db.execute("DELETE FROM student_attendance_settings WHERE student_id=?", (student_id,))


def clear_student_access_log_links(db, student_id: int) -> None:
    db.execute("UPDATE access_logs SET student_id=NULL WHERE student_id=?", (student_id,))


def delete_student_attendance_records(db, student_id: int) -> None:
    db.execute("DELETE FROM attendance_records WHERE student_id=?", (student_id,))


def delete_student_by_id(db, student_id: int) -> None:
    db.execute("DELETE FROM students WHERE id=?", (student_id,))

def count_students(db) -> int:
    return db.execute("SELECT COUNT(*) c FROM students").fetchone()["c"]


def count_active_students(db) -> int:
    return db.execute("SELECT COUNT(*) c FROM students WHERE status='active'").fetchone()["c"]


def count_active_students_with_faces(db) -> int:
    return db.execute(
        """
        SELECT COUNT(DISTINCT f.student_id) c
        FROM student_faces f
        JOIN students s ON s.id = f.student_id
        WHERE s.status='active'
        """
    ).fetchone()["c"]


def count_success_access_logs_today(db, action: str) -> int:
    return db.execute(
        """
        SELECT COUNT(*) c
        FROM access_logs
        WHERE action=? AND result='success' AND date(created_at)=date('now','localtime')
        """,
        (action,),
    ).fetchone()["c"]


def count_alerts_today(db) -> int:
    return db.execute(
        """
        SELECT COUNT(*) c
        FROM alerts
        WHERE date(COALESCE(event_date, created_at))=date('now','localtime')
        """
    ).fetchone()["c"]


def count_attendance_records_today(db, statuses: tuple[str, ...]) -> int:
    placeholders = ",".join("?" for _ in statuses)
    return db.execute(
        f"""
        SELECT COUNT(*) c
        FROM attendance_records
        WHERE status IN ({placeholders}) AND date(attendance_date)=date('now','localtime')
        """,
        statuses,
    ).fetchone()["c"]


def list_recent_access_logs(db, limit: int = 5):
    return db.execute("SELECT * FROM access_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

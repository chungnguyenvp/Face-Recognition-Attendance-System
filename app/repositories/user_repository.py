def student_exists(db, student_id: int) -> bool:
    return db.execute("SELECT id FROM students WHERE id=?", (student_id,)).fetchone() is not None


def list_users_with_students(db, role: str | None = None):
    where = "1=1"
    params = []
    if role:
        where = "u.role = ?"
        params.append(role)
    return db.execute(
        f"""
        SELECT u.id, u.username, u.role, u.student_id, u.status, u.created_at,
               s.student_code, s.full_name, s.class_name
        FROM users u
        LEFT JOIN students s ON s.id = u.student_id
        WHERE {where}
        ORDER BY u.id DESC
        """,
        params,
    ).fetchall()


def create_user(db, username: str, password_hash: str, role: str, student_id: int | None, created_at: str) -> int:
    cur = db.execute(
        """
        INSERT INTO users(username, password_hash, role, student_id, status, created_at)
        VALUES (?, ?, ?, ?, 'active', ?)
        """,
        (username, password_hash, role, student_id, created_at),
    )
    return cur.lastrowid


def get_user_public(db, user_id: int):
    return db.execute(
        "SELECT id, username, role, student_id, status, created_at FROM users WHERE id=?",
        (user_id,),
    ).fetchone()


def get_user_by_id(db, user_id: int):
    return db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()


def get_user_by_username(db, username: str):
    return db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def get_session_user(db, user_id: int):
    return db.execute(
        """
        SELECT id, username, role, student_id, status
        FROM users
        WHERE id = ?
        """,
        (user_id,),
    ).fetchone()


def get_user_delete_summary(db, user_id: int):
    return db.execute(
        "SELECT id, username, role, student_id, status FROM users WHERE id=?",
        (user_id,),
    ).fetchone()


def get_student_user_by_student_id(db, student_id: int):
    return db.execute(
        """
        SELECT id, username, role, student_id, status
        FROM users
        WHERE role='student' AND student_id=?
        """,
        (student_id,),
    ).fetchone()


def update_user_student_id(db, user_id: int, student_id: int) -> None:
    db.execute("UPDATE users SET student_id=? WHERE id=?", (student_id, user_id))


def update_user_password_hash(db, user_id: int, password_hash: str) -> None:
    db.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash, user_id))


def update_user_status(db, user_id: int, status: str) -> None:
    db.execute("UPDATE users SET status=? WHERE id=?", (status, user_id))


def count_active_admins(db, exclude_user_id: int | None = None) -> int:
    if exclude_user_id is None:
        return db.execute("SELECT COUNT(*) c FROM users WHERE role='admin' AND status='active'").fetchone()["c"]
    return db.execute(
        "SELECT COUNT(*) c FROM users WHERE role='admin' AND status='active' AND id<>?",
        (exclude_user_id,),
    ).fetchone()["c"]


def delete_user(db, user_id: int) -> None:
    db.execute("DELETE FROM users WHERE id=?", (user_id,))

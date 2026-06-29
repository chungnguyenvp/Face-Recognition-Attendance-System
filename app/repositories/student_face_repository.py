def list_student_faces(db, student_id: int):
    return db.execute(
        "SELECT id, image_path, created_at FROM student_faces WHERE student_id = ? ORDER BY id DESC",
        (student_id,),
    ).fetchall()


def create_student_face(db, student_id: int, image_path: str, embedding: str, created_at: str) -> int:
    cur = db.execute(
        "INSERT INTO student_faces(student_id, image_path, embedding, created_at) VALUES (?, ?, ?, ?)",
        (student_id, image_path, embedding, created_at),
    )
    return cur.lastrowid


def list_student_face_image_paths(db, student_id: int) -> list[str]:
    rows = db.execute("SELECT image_path FROM student_faces WHERE student_id = ?", (student_id,)).fetchall()
    return [row["image_path"] for row in rows if row["image_path"]]


def delete_student_faces(db, student_id: int) -> None:
    db.execute("DELETE FROM student_faces WHERE student_id = ?", (student_id,))


def count_student_faces(db, student_id: int) -> int:
    return db.execute("SELECT COUNT(*) c FROM student_faces WHERE student_id = ?", (student_id,)).fetchone()["c"]


def list_oldest_student_faces(db, student_id: int, limit: int):
    return db.execute(
        """
        SELECT id, image_path FROM student_faces
        WHERE student_id = ?
        ORDER BY created_at ASC, id ASC
        LIMIT ?
        """,
        (student_id, limit),
    ).fetchall()


def delete_student_faces_by_ids(db, face_ids: list[int]) -> None:
    if not face_ids:
        return
    db.execute(
        f"DELETE FROM student_faces WHERE id IN ({','.join('?' for _ in face_ids)})",
        face_ids,
    )


def get_student_face(db, student_id: int, face_id: int):
    return db.execute(
        "SELECT image_path FROM student_faces WHERE id=? AND student_id=?",
        (face_id, student_id),
    ).fetchone()


def delete_student_face(db, student_id: int, face_id: int) -> None:
    db.execute("DELETE FROM student_faces WHERE id=? AND student_id=?", (face_id, student_id))


def list_active_face_embeddings_except_student(db, student_id: int):
    return db.execute(
        """
        SELECT f.embedding, s.id student_id, s.student_code, s.full_name
        FROM student_faces f
        JOIN students s ON s.id = f.student_id
        WHERE s.status='active' AND s.id != ?
        """,
        (student_id,),
    ).fetchall()


def list_active_face_embeddings(db):
    return db.execute(
        """
        SELECT f.embedding, s.id student_id, s.student_code, s.full_name
        FROM student_faces f
        JOIN students s ON s.id = f.student_id
        WHERE s.status='active'
        """
    ).fetchall()

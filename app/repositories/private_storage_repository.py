_EVIDENCE_TABLES = {"access_logs", "alerts"}


def list_legacy_student_faces(db):
    return db.execute(
        """
        SELECT id, image_path
        FROM student_faces
        WHERE image_path LIKE '/static/uploads/faces/%'
           OR image_path LIKE 'web/static/uploads/faces/%'
           OR image_path LIKE 'static/uploads/faces/%'
           OR image_path LIKE 'storage/private/faces/%'
        """
    ).fetchall()


def update_student_face_path(db, face_id: int, image_path: str) -> None:
    db.execute("UPDATE student_faces SET image_path=? WHERE id=?", (image_path, face_id))


def list_legacy_evidence_paths(db, table_name: str):
    table = _validated_evidence_table(table_name)
    return db.execute(
        f"""
        SELECT id, evidence_image_path
        FROM {table}
        WHERE evidence_image_path LIKE '/static/uploads/evidence/%'
           OR evidence_image_path LIKE 'web/static/uploads/evidence/%'
           OR evidence_image_path LIKE 'static/uploads/evidence/%'
           OR evidence_image_path LIKE 'storage/private/evidence/%'
        """
    ).fetchall()


def update_evidence_path(db, table_name: str, record_id: int, evidence_image_path: str) -> None:
    table = _validated_evidence_table(table_name)
    db.execute(f"UPDATE {table} SET evidence_image_path=? WHERE id=?", (evidence_image_path, record_id))


def _validated_evidence_table(table_name: str) -> str:
    if table_name not in _EVIDENCE_TABLES:
        raise ValueError("Unsupported evidence table.")
    return table_name

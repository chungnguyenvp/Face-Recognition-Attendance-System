def get_student_face_file(db, face_id: int):
    return db.execute(
        """
        SELECT id, student_id, image_path
        FROM student_faces
        WHERE id = ?
        """,
        (face_id,),
    ).fetchone()


def get_access_log_evidence_file(db, log_id: int):
    return db.execute(
        """
        SELECT id, student_id, evidence_image_path
        FROM access_logs
        WHERE id = ?
        """,
        (log_id,),
    ).fetchone()


def get_alert_evidence_file(db, alert_id: int):
    return db.execute(
        """
        SELECT id, evidence_image_path
        FROM alerts
        WHERE id = ?
        """,
        (alert_id,),
    ).fetchone()

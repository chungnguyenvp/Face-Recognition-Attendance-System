from app.repositories.query_filters import append_alert_event_date_filters


def list_alerts(
    db,
    limit: int,
    date_from: str | None = None,
    date_to: str | None = None,
    alert_type: str | None = None,
    status: str | None = None,
    q: str | None = None,
):
    clauses = ["1=1"]
    params = []
    append_alert_event_date_filters(clauses, params, date_from, date_to)
    if alert_type:
        clauses.append("type=?")
        params.append(alert_type)
    if status:
        clauses.append("status=?")
        params.append(status)
    if q:
        clauses.append("message LIKE ?")
        params.append(f"%{q}%")
    safe_limit = max(1, min(int(limit), 500))
    return db.execute(
        f"SELECT * FROM alerts WHERE {' AND '.join(clauses)} ORDER BY id DESC LIMIT ?",
        (*params, safe_limit),
    ).fetchall()


def get_alert_summary(db, alert_id: int):
    return db.execute(
        "SELECT id, type, message, status FROM alerts WHERE id=?",
        (alert_id,),
    ).fetchone()


def get_alert_by_id(db, alert_id: int):
    return db.execute("SELECT * FROM alerts WHERE id=?", (alert_id,)).fetchone()


def get_alert_by_type_and_message_tokens(db, alert_type: str, first_token: str, second_token: str):
    return db.execute(
        "SELECT id FROM alerts WHERE type=? AND message LIKE ? AND message LIKE ? LIMIT 1",
        (alert_type, f"%{first_token}%", f"%{second_token}%"),
    ).fetchone()


def update_alert_status(db, alert_id: int, status: str) -> None:
    db.execute("UPDATE alerts SET status=? WHERE id=?", (status, alert_id))


def create_alert(db, alert_type: str, message: str, evidence_image_path: str | None, event_date: str, created_at: str) -> None:
    db.execute(
        "INSERT INTO alerts(type, message, status, evidence_image_path, event_date, created_at) VALUES (?, ?, 'new', ?, ?, ?)",
        (alert_type, message, evidence_image_path, event_date, created_at),
    )


def delete_alert(db, alert_id: int) -> None:
    db.execute("DELETE FROM alerts WHERE id=?", (alert_id,))

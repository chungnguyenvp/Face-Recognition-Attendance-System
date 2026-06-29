from app.repositories.query_filters import append_created_date_filters


def create_audit_log(
    db,
    actor_user_id: int | None,
    actor_username: str | None,
    actor_role: str | None,
    action: str,
    entity_type: str,
    entity_id: str | None,
    entity_label: str | None,
    details_json: str,
    ip_address: str | None,
    user_agent: str | None,
    created_at: str,
) -> None:
    db.execute(
        """
        INSERT INTO audit_logs(
            actor_user_id, actor_username, actor_role, action, entity_type,
            entity_id, entity_label, details_json, ip_address, user_agent, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            actor_user_id,
            actor_username,
            actor_role,
            action,
            entity_type,
            entity_id,
            entity_label,
            details_json,
            ip_address,
            user_agent,
            created_at,
        ),
    )


def list_audit_logs(
    db,
    limit: int,
    date_from: str | None = None,
    date_to: str | None = None,
    actor: str | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    q: str | None = None,
):
    clauses = ["1=1"]
    params = []
    append_created_date_filters(clauses, params, date_from, date_to)
    if actor:
        clauses.append("actor_username LIKE ?")
        params.append(f"%{actor}%")
    if action:
        clauses.append("action LIKE ?")
        params.append(f"%{action}%")
    if entity_type:
        clauses.append("entity_type=?")
        params.append(entity_type)
    if q:
        clauses.append("(entity_label LIKE ? OR details_json LIKE ? OR action LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])

    safe_limit = max(1, min(int(limit), 1000))
    return db.execute(
        f"""
        SELECT *
        FROM audit_logs
        WHERE {' AND '.join(clauses)}
        ORDER BY id DESC
        LIMIT ?
        """,
        (*params, safe_limit),
    ).fetchall()

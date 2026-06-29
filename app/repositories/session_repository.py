def create_session(
    db,
    session_id: str,
    user_id: int,
    created_at: int,
    expires_at: int,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    db.execute(
        """
        INSERT INTO user_sessions(
            session_id, user_id, created_at, expires_at, revoked_at,
            ip_address, user_agent
        )
        VALUES (?, ?, ?, ?, NULL, ?, ?)
        """,
        (session_id, user_id, created_at, expires_at, ip_address, user_agent),
    )


def revoke_session(db, session_id: str, revoked_at: int) -> None:
    db.execute(
        """
        UPDATE user_sessions
        SET revoked_at = COALESCE(revoked_at, ?)
        WHERE session_id = ?
        """,
        (revoked_at, session_id),
    )


def revoke_user_sessions(db, user_id: int, revoked_at: int) -> None:
    db.execute(
        """
        UPDATE user_sessions
        SET revoked_at = COALESCE(revoked_at, ?)
        WHERE user_id = ? AND revoked_at IS NULL
        """,
        (revoked_at, user_id),
    )


def get_active_session(db, session_id: str, user_id: int, now: int):
    return db.execute(
        """
        SELECT session_id, user_id, expires_at, revoked_at
        FROM user_sessions
        WHERE session_id = ?
          AND user_id = ?
          AND revoked_at IS NULL
          AND expires_at > ?
        """,
        (session_id, user_id, now),
    ).fetchone()

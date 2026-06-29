def get_retry_state(db, attempt_key: str):
    return db.execute(
        """
        SELECT first_failed_at, locked_until
        FROM login_rate_limits
        WHERE attempt_key = ?
        """,
        (attempt_key,),
    ).fetchone()


def clear_attempt(db, attempt_key: str) -> None:
    db.execute("DELETE FROM login_rate_limits WHERE attempt_key = ?", (attempt_key,))


def upsert_failure(
    db,
    attempt_key: str,
    now: int,
    window_start: int,
    max_attempts: int,
    lock_expires_at: int,
) -> None:
    db.execute(
        """
        INSERT INTO login_rate_limits(
            attempt_key, failed_attempts, first_failed_at, locked_until, updated_at
        )
        VALUES (?, 1, ?, NULL, ?)
        ON CONFLICT(attempt_key) DO UPDATE SET
            failed_attempts = CASE
                WHEN login_rate_limits.first_failed_at <= ?
                  OR (
                      login_rate_limits.locked_until IS NOT NULL
                      AND login_rate_limits.locked_until <= ?
                  )
                THEN 1
                ELSE login_rate_limits.failed_attempts + 1
            END,
            first_failed_at = CASE
                WHEN login_rate_limits.first_failed_at <= ?
                  OR (
                      login_rate_limits.locked_until IS NOT NULL
                      AND login_rate_limits.locked_until <= ?
                  )
                THEN ?
                ELSE login_rate_limits.first_failed_at
            END,
            locked_until = CASE
                WHEN login_rate_limits.first_failed_at <= ?
                  OR (
                      login_rate_limits.locked_until IS NOT NULL
                      AND login_rate_limits.locked_until <= ?
                  )
                THEN NULL
                WHEN login_rate_limits.failed_attempts + 1 >= ?
                THEN ?
                ELSE login_rate_limits.locked_until
            END,
            updated_at = ?
        """,
        (
            attempt_key,
            now,
            now,
            window_start,
            now,
            window_start,
            now,
            now,
            window_start,
            now,
            max_attempts,
            lock_expires_at,
            now,
        ),
    )


def get_failure_state(db, attempt_key: str):
    return db.execute(
        """
        SELECT failed_attempts, locked_until
        FROM login_rate_limits
        WHERE attempt_key = ?
        """,
        (attempt_key,),
    ).fetchone()

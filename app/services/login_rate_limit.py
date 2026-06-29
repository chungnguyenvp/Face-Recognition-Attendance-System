import hashlib
import time

from app.core.config import settings
from app.repositories import login_rate_limit_repository


def login_attempt_key(request, username: str) -> str:
    client_ip = request.client.host if request.client else "unknown"
    normalized_username = username.strip().casefold()
    raw_key = f"{client_ip}\0{normalized_username}".encode("utf-8")
    return hashlib.sha256(raw_key).hexdigest()


def login_retry_after(db, attempt_key: str, now: int | None = None) -> int:
    now = int(time.time()) if now is None else now
    row = login_rate_limit_repository.get_retry_state(db, attempt_key)
    if not row:
        return 0

    locked_until = row["locked_until"]
    if locked_until and locked_until > now:
        return locked_until - now

    window_start = now - settings.login_attempt_window_seconds
    if row["first_failed_at"] <= window_start or (locked_until and locked_until <= now):
        login_rate_limit_repository.clear_attempt(db, attempt_key)
    return 0


def record_login_failure(db, attempt_key: str, now: int | None = None) -> dict:
    now = int(time.time()) if now is None else now
    window_start = now - settings.login_attempt_window_seconds
    max_attempts = settings.login_max_failed_attempts
    lock_expires_at = now + settings.login_lockout_seconds

    login_rate_limit_repository.upsert_failure(
        db,
        attempt_key,
        now,
        window_start,
        max_attempts,
        lock_expires_at,
    )
    row = login_rate_limit_repository.get_failure_state(db, attempt_key)
    failed_attempts = row["failed_attempts"]
    return {
        "failed_attempts": failed_attempts,
        "remaining_attempts": max(0, max_attempts - failed_attempts),
        "locked_until": row["locked_until"],
    }


def clear_login_failures(db, attempt_key: str) -> None:
    login_rate_limit_repository.clear_attempt(db, attempt_key)

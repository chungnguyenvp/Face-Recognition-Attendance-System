import sqlite3
import unittest

from app.core.security import create_session_token, parse_session_token
from app.services.session_service import (
    active_session_row,
    create_user_session,
    revoke_session,
    revoke_user_sessions,
)


class SessionServiceTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute(
            """
            CREATE TABLE user_sessions (
                session_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                revoked_at INTEGER,
                ip_address TEXT,
                user_agent TEXT
            )
            """
        )

    def tearDown(self):
        self.db.close()

    def test_created_session_is_active(self):
        session_id = create_user_session(self.db, 7, now=1_000)

        row = active_session_row(self.db, session_id, 7, now=1_001)

        self.assertIsNotNone(row)

    def test_revoked_session_is_inactive(self):
        session_id = create_user_session(self.db, 7, now=1_000)
        revoke_session(self.db, session_id, now=1_001)

        row = active_session_row(self.db, session_id, 7, now=1_002)

        self.assertIsNone(row)

    def test_revoke_user_sessions_revokes_all_sessions(self):
        first = create_user_session(self.db, 7, now=1_000)
        second = create_user_session(self.db, 7, now=1_000)
        other_user = create_user_session(self.db, 8, now=1_000)

        revoke_user_sessions(self.db, 7, now=1_001)

        self.assertIsNone(active_session_row(self.db, first, 7, now=1_002))
        self.assertIsNone(active_session_row(self.db, second, 7, now=1_002))
        self.assertIsNotNone(active_session_row(self.db, other_user, 8, now=1_002))

    def test_expired_session_is_inactive(self):
        session_id = create_user_session(self.db, 7, now=1_000)
        expires_at = self.db.execute(
            "SELECT expires_at FROM user_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()["expires_at"]

        self.assertIsNone(active_session_row(self.db, session_id, 7, now=expires_at))

    def test_token_contains_signed_session_id(self):
        token = create_session_token(7, "session-test")

        data = parse_session_token(token)

        self.assertEqual(data["user_id"], 7)
        self.assertEqual(data["session_id"], "session-test")

    def test_signed_token_is_rejected_after_its_database_session_is_revoked(self):
        session_id = create_user_session(self.db, 7)
        token = create_session_token(7, session_id)
        data = parse_session_token(token)

        self.assertIsNotNone(active_session_row(self.db, data["session_id"], data["user_id"]))

        revoke_session(self.db, session_id)

        self.assertIsNone(active_session_row(self.db, data["session_id"], data["user_id"]))


if __name__ == "__main__":
    unittest.main()

import sqlite3
import unittest

from app.services.login_rate_limit import (
    clear_login_failures,
    login_retry_after,
    record_login_failure,
)


class LoginRateLimitTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute(
            """
            CREATE TABLE login_rate_limits (
                attempt_key TEXT PRIMARY KEY,
                failed_attempts INTEGER NOT NULL,
                first_failed_at INTEGER NOT NULL,
                locked_until INTEGER,
                updated_at INTEGER NOT NULL
            )
            """
        )
        self.attempt_key = "test-attempt-key"

    def tearDown(self):
        self.db.close()

    def test_blocks_after_ten_failed_attempts(self):
        for attempt in range(1, 11):
            state = record_login_failure(self.db, self.attempt_key, now=1_000)
            self.assertEqual(state["failed_attempts"], attempt)

        self.assertEqual(login_retry_after(self.db, self.attempt_key, now=1_000), 900)

    def test_lock_expires_after_fifteen_minutes(self):
        for _ in range(10):
            record_login_failure(self.db, self.attempt_key, now=1_000)

        self.assertEqual(login_retry_after(self.db, self.attempt_key, now=1_899), 1)
        self.assertEqual(login_retry_after(self.db, self.attempt_key, now=1_900), 0)

    def test_success_clears_failed_attempts(self):
        record_login_failure(self.db, self.attempt_key, now=1_000)
        clear_login_failures(self.db, self.attempt_key)

        row = self.db.execute(
            "SELECT 1 FROM login_rate_limits WHERE attempt_key = ?",
            (self.attempt_key,),
        ).fetchone()
        self.assertIsNone(row)

    def test_old_attempt_window_starts_a_new_counter(self):
        record_login_failure(self.db, self.attempt_key, now=1_000)
        state = record_login_failure(self.db, self.attempt_key, now=1_901)

        self.assertEqual(state["failed_attempts"], 1)
        self.assertEqual(state["remaining_attempts"], 9)


if __name__ == "__main__":
    unittest.main()

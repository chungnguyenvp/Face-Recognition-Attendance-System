import base64
from contextlib import contextmanager
import hashlib
import sqlite3
import unittest


class PasswordSecurityTests(unittest.TestCase):
    def setUp(self):
        try:
            from app.core import security
        except ModuleNotFoundError as exc:
            self.skipTest(f"{exc.name} is not installed in this test environment.")

        self.security = security
        self.original_iterations = security.settings.password_pbkdf2_iterations
        security.settings.password_pbkdf2_iterations = 1_000

    def tearDown(self):
        if hasattr(self, "security"):
            self.security.settings.password_pbkdf2_iterations = self.original_iterations

    def legacy_hash(self, password: str, salt: bytes) -> str:
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            self.security.LEGACY_PBKDF2_ITERATIONS,
        )
        return base64.b64encode(salt + digest).decode("utf-8")

    def test_new_password_hash_stores_algorithm_and_iterations(self):
        stored = self.security.hash_password("secret-password", salt=b"1" * 16)

        self.assertTrue(stored.startswith("pbkdf2_sha256$1000$"))
        self.assertTrue(self.security.verify_password("secret-password", stored))
        self.assertFalse(self.security.verify_password("wrong-password", stored))
        self.assertFalse(self.security.password_needs_rehash(stored))

    def test_lower_iteration_hash_needs_rehash(self):
        stored = self.security.hash_password("secret-password", salt=b"2" * 16)

        self.security.settings.password_pbkdf2_iterations = 2_000

        self.assertTrue(self.security.verify_password("secret-password", stored))
        self.assertTrue(self.security.password_needs_rehash(stored))

    def test_legacy_hash_still_verifies_and_needs_rehash(self):
        stored = self.legacy_hash("secret-password", b"3" * 16)

        self.assertTrue(self.security.verify_password("secret-password", stored))
        self.assertFalse(self.security.verify_password("wrong-password", stored))
        self.assertTrue(self.security.password_needs_rehash(stored))


class LoginPasswordRehashTests(unittest.TestCase):
    def setUp(self):
        try:
            from fastapi import Request, Response
            from app.core import security
            from app.routers import auth
        except ModuleNotFoundError as exc:
            self.skipTest(f"{exc.name} is not installed in this test environment.")

        self.Request = Request
        self.Response = Response
        self.security = security
        self.auth = auth
        self.original_iterations = security.settings.password_pbkdf2_iterations
        self.original_get_db = auth.get_db
        security.settings.password_pbkdf2_iterations = 1_000

        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL,
                student_id INTEGER,
                created_at TEXT NOT NULL
            );
            CREATE TABLE login_rate_limits (
                attempt_key TEXT PRIMARY KEY,
                failed_attempts INTEGER NOT NULL,
                first_failed_at INTEGER NOT NULL,
                locked_until INTEGER,
                updated_at INTEGER NOT NULL
            );
            CREATE TABLE user_sessions (
                session_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                revoked_at INTEGER,
                ip_address TEXT,
                user_agent TEXT
            );
            CREATE TABLE audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_user_id INTEGER,
                actor_username TEXT,
                actor_role TEXT,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT,
                entity_label TEXT,
                details_json TEXT,
                ip_address TEXT,
                user_agent TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        self.db.execute(
            """
            INSERT INTO users(id, username, password_hash, role, status, created_at)
            VALUES (1, 'legacy-user', ?, 'admin', 'active', '2026-01-01T00:00:00')
            """,
            (self.legacy_hash("correct-password", b"4" * 16),),
        )

        @contextmanager
        def test_get_db():
            try:
                yield self.db
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise

        auth.get_db = test_get_db

    def tearDown(self):
        if hasattr(self, "auth"):
            self.auth.get_db = self.original_get_db
            self.security.settings.password_pbkdf2_iterations = self.original_iterations
        if hasattr(self, "db"):
            self.db.close()

    def legacy_hash(self, password: str, salt: bytes) -> str:
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            self.security.LEGACY_PBKDF2_ITERATIONS,
        )
        return base64.b64encode(salt + digest).decode("utf-8")

    def test_successful_login_upgrades_legacy_password_hash(self):
        request = self.Request(
            {
                "type": "http",
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": "/api/auth/login",
                "raw_path": b"/api/auth/login",
                "query_string": b"",
                "headers": [],
                "client": ("127.0.0.1", 12345),
                "server": ("testserver", 80),
            }
        )

        result = self.auth.login(
            self.auth.LoginRequest(username="legacy-user", password="correct-password"),
            self.Response(),
            request,
        )

        stored = self.db.execute("SELECT password_hash FROM users WHERE id=1").fetchone()["password_hash"]
        self.assertTrue(result["ok"])
        self.assertTrue(stored.startswith("pbkdf2_sha256$1000$"))
        self.assertTrue(self.security.verify_password("correct-password", stored))


if __name__ == "__main__":
    unittest.main()

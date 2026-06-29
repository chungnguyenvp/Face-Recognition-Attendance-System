import json
import sqlite3
import unittest
from types import SimpleNamespace

from app.services.audit_service import audit_diff, write_audit_log


class AuditServiceTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute(
            """
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
            )
            """
        )

    def tearDown(self):
        self.db.close()

    def test_write_audit_log_stores_actor_request_and_details(self):
        request = SimpleNamespace(
            headers={
                "x-forwarded-for": "203.0.113.10, 10.0.0.2",
                "user-agent": "audit-test",
            },
            client=SimpleNamespace(host="127.0.0.1"),
        )

        write_audit_log(
            self.db,
            {"id": 7, "username": "admin", "role": "admin"},
            "students.update",
            "student",
            42,
            "SV042",
            {"changes": {"status": {"old": "active", "new": "inactive"}}},
            request,
        )

        row = self.db.execute("SELECT * FROM audit_logs").fetchone()
        self.assertEqual(row["actor_user_id"], 7)
        self.assertEqual(row["actor_username"], "admin")
        self.assertEqual(row["actor_role"], "admin")
        self.assertEqual(row["entity_id"], "42")
        self.assertEqual(row["ip_address"], "203.0.113.10")
        self.assertEqual(row["user_agent"], "audit-test")
        self.assertEqual(
            json.loads(row["details_json"]),
            {"changes": {"status": {"old": "active", "new": "inactive"}}},
        )

    def test_audit_diff_only_returns_changed_values(self):
        changes = audit_diff(
            {"full_name": "Nguyen Van A", "status": "active"},
            {"full_name": "Nguyen Van A", "status": "inactive"},
            ["full_name", "status"],
        )

        self.assertEqual(
            changes,
            {"status": {"old": "active", "new": "inactive"}},
        )


if __name__ == "__main__":
    unittest.main()

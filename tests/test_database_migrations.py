import sqlite3
import tempfile
import unittest
from pathlib import Path

from app import db as db_module
from app.migrations import (
    FACE_REQUEST_CONSTRAINTS_VERSION,
    LEGACY_CAMERA_SETTING_KEYS,
    REMOVE_LEGACY_CAMERA_SETTINGS_VERSION,
    USERS_STUDENT_FK_VERSION,
)


class DatabaseMigrationTests(unittest.TestCase):
    def setUp(self):
        self.original_database_path = db_module.settings.database_path
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "legacy_face_lab.db"
        db_module.settings.database_path = str(self.database_path)
        self._create_legacy_database()

    def tearDown(self):
        db_module.settings.database_path = self.original_database_path
        self.temp_dir.cleanup()

    def _create_legacy_database(self):
        db = sqlite3.connect(self.database_path)
        db.executescript(
            """
            CREATE TABLE students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_code TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                class_name TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL
            );

            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'admin',
                student_id INTEGER,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL
            );

            CREATE TABLE user_sessions (
                session_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                revoked_at INTEGER,
                ip_address TEXT,
                user_agent TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE face_registration_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending', 'approved', 'rejected', 'cancelled')),
                storage_key TEXT NOT NULL,
                front_image_path TEXT NOT NULL,
                left_image_path TEXT NOT NULL,
                right_image_path TEXT NOT NULL,
                up_image_path TEXT NOT NULL,
                down_image_path TEXT NOT NULL,
                note TEXT,
                reject_reason TEXT,
                reviewed_by INTEGER,
                reviewed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE,
                FOREIGN KEY(reviewed_by) REFERENCES users(id) ON DELETE SET NULL
            );

            CREATE TABLE settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        db.executemany(
            "INSERT INTO settings(key, value) VALUES (?, 'legacy-value')",
            [(key,) for key in LEGACY_CAMERA_SETTING_KEYS],
        )
        db.execute(
            """
            INSERT INTO students(
                id, student_code, full_name, class_name, status, created_at
            ) VALUES (1, 'SV001', 'Student One', 'LAB', 'active', '2026-01-01')
            """
        )
        db.executemany(
            """
            INSERT INTO users(
                id, username, password_hash, role, student_id, status, created_at
            ) VALUES (?, ?, 'hash', ?, ?, 'active', '2026-01-01')
            """,
            [
                (1, db_module.settings.default_admin_username, "admin", None),
                (2, "valid-student", "student", 1),
                (3, "orphan-student", "student", 999),
            ],
        )
        db.execute(
            """
            INSERT INTO user_sessions(
                session_id, user_id, created_at, expires_at,
                revoked_at, ip_address, user_agent
            ) VALUES ('orphan-session', 3, 1, 9999999999, NULL, NULL, NULL)
            """
        )
        db.execute(
            """
            INSERT INTO face_registration_requests(
                id, student_id, status, storage_key,
                front_image_path, left_image_path, right_image_path,
                up_image_path, down_image_path,
                note, reject_reason, reviewed_by, reviewed_at,
                created_at, updated_at
            ) VALUES (
                1, 1, 'pending', 'request-1',
                'front.jpg', 'left.jpg', 'right.jpg',
                'up.jpg', 'down.jpg',
                NULL, NULL, NULL, NULL,
                '2026-01-01', '2026-01-01'
            )
            """
        )
        db.commit()
        db.close()

    def test_init_db_upgrades_constraints_and_repairs_orphan_user(self):
        db_module.init_db()

        with db_module.get_db() as db:
            foreign_keys = db.execute("PRAGMA foreign_key_list(users)").fetchall()
            valid_user = db.execute("SELECT * FROM users WHERE id=2").fetchone()
            orphan_user = db.execute("SELECT * FROM users WHERE id=3").fetchone()
            orphan_session = db.execute(
                "SELECT * FROM user_sessions WHERE session_id='orphan-session'"
            ).fetchone()
            face_request = db.execute(
                "SELECT * FROM face_registration_requests WHERE id=1"
            ).fetchone()
            migration_versions = {
                row["version"]
                for row in db.execute(
                    "SELECT version FROM schema_migrations"
                ).fetchall()
            }
            legacy_camera_setting_count = db.execute(
                f"SELECT COUNT(*) FROM settings WHERE key IN ({', '.join('?' for _ in LEGACY_CAMERA_SETTING_KEYS)})",
                LEGACY_CAMERA_SETTING_KEYS,
            ).fetchone()[0]

        self.assertTrue(
            any(
                row["from"] == "student_id"
                and row["table"] == "students"
                and row["on_delete"].upper() == "SET NULL"
                for row in foreign_keys
            )
        )
        self.assertEqual(valid_user["student_id"], 1)
        self.assertEqual(valid_user["status"], "active")
        self.assertIsNone(orphan_user["student_id"])
        self.assertEqual(orphan_user["status"], "inactive")
        self.assertIsNotNone(orphan_session["revoked_at"])
        self.assertEqual(face_request["request_type"], "initial")
        self.assertEqual(face_request["face_count_at_submit"], 0)
        self.assertEqual(face_request["planned_remove_count"], 0)
        self.assertEqual(
            migration_versions,
            {
                USERS_STUDENT_FK_VERSION,
                FACE_REQUEST_CONSTRAINTS_VERSION,
                REMOVE_LEGACY_CAMERA_SETTINGS_VERSION,
            },
        )
        self.assertEqual(legacy_camera_setting_count, 0)

    def test_upgraded_database_enforces_new_constraints(self):
        db_module.init_db()

        with self.assertRaises(sqlite3.IntegrityError):
            with db_module.get_db() as db:
                db.execute("UPDATE users SET student_id=999 WHERE id=2")

        with self.assertRaises(sqlite3.IntegrityError):
            with db_module.get_db() as db:
                db.execute(
                    """
                    UPDATE face_registration_requests
                    SET request_type='invalid'
                    WHERE id=1
                    """
                )

    def test_schema_migrations_are_idempotent(self):
        db_module.init_db()
        db_module.init_db()

        with db_module.get_db() as db:
            user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            request_count = db.execute(
                "SELECT COUNT(*) FROM face_registration_requests"
            ).fetchone()[0]
            migration_count = db.execute(
                "SELECT COUNT(*) FROM schema_migrations"
            ).fetchone()[0]

        self.assertEqual(user_count, 3)
        self.assertEqual(request_count, 1)
        self.assertEqual(migration_count, 3)


if __name__ == "__main__":
    unittest.main()

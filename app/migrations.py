import re
import sqlite3
from datetime import datetime


USERS_STUDENT_FK_VERSION = 2026071401
FACE_REQUEST_CONSTRAINTS_VERSION = 2026071402


def run_schema_migrations(db: sqlite3.Connection) -> None:
    _ensure_schema_migrations_table(db)
    _migrate_users_student_foreign_key(db)
    _migrate_face_registration_request_constraints(db)


def _ensure_schema_migrations_table(db: sqlite3.Connection) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )


def _migration_applied(db: sqlite3.Connection, version: int) -> bool:
    row = db.execute(
        "SELECT version FROM schema_migrations WHERE version=?",
        (version,),
    ).fetchone()
    return row is not None


def _record_migration(db: sqlite3.Connection, version: int, name: str) -> None:
    db.execute(
        """
        INSERT OR IGNORE INTO schema_migrations(version, name, applied_at)
        VALUES (?, ?, ?)
        """,
        (version, name, datetime.now().isoformat(timespec="seconds")),
    )


def _table_exists(db: sqlite3.Connection, table_name: str) -> bool:
    row = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _column_names(db: sqlite3.Connection, table_name: str) -> set[str]:
    return {
        row["name"]
        for row in db.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


def _users_student_foreign_key_exists(db: sqlite3.Connection) -> bool:
    return any(
        row["from"] == "student_id"
        and row["table"] == "students"
        and row["to"] == "id"
        and row["on_delete"].upper() == "SET NULL"
        for row in db.execute("PRAGMA foreign_key_list(users)").fetchall()
    )


def _migrate_users_student_foreign_key(db: sqlite3.Connection) -> None:
    migration_name = "rebuild users with student foreign key"
    migration_applied = _migration_applied(db, USERS_STUDENT_FK_VERSION)
    if _users_student_foreign_key_exists(db):
        if not migration_applied:
            _record_migration(db, USERS_STUDENT_FK_VERSION, migration_name)
        return
    if migration_applied:
        raise RuntimeError(
            "Migration users/student foreign key is marked as applied, "
            "but the foreign key is missing."
        )

    columns = _column_names(db, "users")
    required_columns = {"id", "username", "password_hash", "role", "created_at"}
    missing_columns = required_columns - columns
    if missing_columns:
        raise RuntimeError(
            "Cannot migrate users table; missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    duplicate_links = []
    orphan_student_user_ids = []
    if "student_id" in columns:
        duplicate_links = db.execute(
            """
            SELECT student_id, COUNT(*) AS count
            FROM users
            WHERE student_id IS NOT NULL
            GROUP BY student_id
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        orphan_student_user_ids = [
            row["id"]
            for row in db.execute(
                """
                SELECT u.id
                FROM users u
                LEFT JOIN students s ON s.id=u.student_id
                WHERE u.role='student'
                  AND u.student_id IS NOT NULL
                  AND s.id IS NULL
                """
            ).fetchall()
        ]
    if duplicate_links:
        raise RuntimeError(
            "Cannot migrate users table because multiple users are linked "
            "to the same student. Resolve duplicate links first."
        )

    student_id_expression = "NULL"
    invalid_student_condition = "0"
    if "student_id" in columns:
        invalid_student_condition = (
            "u.student_id IS NOT NULL AND "
            "NOT EXISTS(SELECT 1 FROM students s WHERE s.id=u.student_id)"
        )
        student_id_expression = (
            "CASE WHEN u.student_id IS NULL OR "
            "EXISTS(SELECT 1 FROM students s WHERE s.id=u.student_id) "
            "THEN u.student_id ELSE NULL END"
        )
    status_expression = "'active'"
    if "status" in columns:
        status_expression = "COALESCE(u.status, 'active')"
    if "student_id" in columns:
        status_expression = (
            "CASE WHEN u.role='student' AND "
            f"{invalid_student_condition} THEN 'inactive' "
            f"ELSE {status_expression} END"
        )

    _prepare_rebuild(db)
    try:
        db.execute("BEGIN IMMEDIATE")
        if orphan_student_user_ids and _table_exists(db, "user_sessions"):
            session_columns = _column_names(db, "user_sessions")
            if "revoked_at" in session_columns:
                placeholders = ",".join("?" for _ in orphan_student_user_ids)
                revoked_at = int(datetime.now().timestamp())
                db.execute(
                    f"""
                    UPDATE user_sessions
                    SET revoked_at=COALESCE(revoked_at, ?)
                    WHERE user_id IN ({placeholders})
                    """,
                    (revoked_at, *orphan_student_user_ids),
                )

        old_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        db.execute(
            """
            CREATE TABLE users_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'admin',
                student_id INTEGER,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE SET NULL
            )
            """
        )
        db.execute(
            f"""
            INSERT INTO users_new(
                id, username, password_hash, role, student_id, status, created_at
            )
            SELECT
                u.id,
                u.username,
                u.password_hash,
                u.role,
                {student_id_expression},
                {status_expression},
                u.created_at
            FROM users u
            """
        )
        new_count = db.execute("SELECT COUNT(*) FROM users_new").fetchone()[0]
        if new_count != old_count:
            raise RuntimeError("Users migration changed the number of user records.")

        db.execute("DROP TABLE users")
        db.execute("ALTER TABLE users_new RENAME TO users")
        db.execute("CREATE INDEX idx_users_role ON users(role)")
        db.execute(
            """
            CREATE UNIQUE INDEX idx_users_student_id_unique
            ON users(student_id)
            WHERE student_id IS NOT NULL
            """
        )
        _record_migration(db, USERS_STUDENT_FK_VERSION, migration_name)
        _raise_on_foreign_key_violations(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        _restore_foreign_keys(db)


def _face_request_has_target_constraints(db: sqlite3.Connection) -> bool:
    columns = {
        row["name"]: row
        for row in db.execute(
            "PRAGMA table_info(face_registration_requests)"
        ).fetchall()
    }
    required = {"request_type", "face_count_at_submit", "planned_remove_count"}
    if not required.issubset(columns):
        return False
    if not all(columns[name]["notnull"] == 1 for name in required):
        return False

    row = db.execute(
        """
        SELECT sql FROM sqlite_master
        WHERE type='table' AND name='face_registration_requests'
        """
    ).fetchone()
    table_sql = row["sql"] if row and row["sql"] else ""
    return bool(
        re.search(
            r"CHECK\s*\(\s*request_type\s+IN\s*\(\s*'initial'\s*,\s*'update'\s*\)\s*\)",
            table_sql,
            re.IGNORECASE,
        )
    )


def _migrate_face_registration_request_constraints(
    db: sqlite3.Connection,
) -> None:
    migration_name = "rebuild face registration request constraints"
    migration_applied = _migration_applied(
        db, FACE_REQUEST_CONSTRAINTS_VERSION
    )
    if _face_request_has_target_constraints(db):
        if not migration_applied:
            _record_migration(
                db, FACE_REQUEST_CONSTRAINTS_VERSION, migration_name
            )
        return
    if migration_applied:
        raise RuntimeError(
            "Face request constraint migration is marked as applied, "
            "but the target constraints are missing."
        )

    columns = _column_names(db, "face_registration_requests")
    required_columns = {
        "id",
        "student_id",
        "status",
        "storage_key",
        "front_image_path",
        "left_image_path",
        "right_image_path",
        "up_image_path",
        "down_image_path",
        "note",
        "reject_reason",
        "reviewed_by",
        "reviewed_at",
        "created_at",
        "updated_at",
    }
    missing_columns = required_columns - columns
    if missing_columns:
        raise RuntimeError(
            "Cannot migrate face registration requests; missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    if "request_type" in columns:
        invalid_rows = db.execute(
            """
            SELECT id
            FROM face_registration_requests
            WHERE request_type IS NULL
               OR request_type NOT IN ('initial', 'update')
            LIMIT 20
            """
        ).fetchall()
        if invalid_rows:
            invalid_ids = ", ".join(str(row["id"]) for row in invalid_rows)
            raise RuntimeError(
                "Invalid face registration request_type values exist for IDs: "
                + invalid_ids
            )

    duplicate_pending = db.execute(
        """
        SELECT student_id
        FROM face_registration_requests
        WHERE status='pending'
        GROUP BY student_id
        HAVING COUNT(*) > 1
        LIMIT 20
        """
    ).fetchall()
    if duplicate_pending:
        raise RuntimeError(
            "Cannot migrate face registration requests because a student "
            "has multiple pending requests."
        )

    request_type_expression = (
        "request_type" if "request_type" in columns else "'initial'"
    )
    face_count_expression = (
        "COALESCE(face_count_at_submit, 0)"
        if "face_count_at_submit" in columns
        else "0"
    )
    planned_remove_expression = (
        "COALESCE(planned_remove_count, 0)"
        if "planned_remove_count" in columns
        else "0"
    )

    _prepare_rebuild(db)
    try:
        db.execute("BEGIN IMMEDIATE")
        old_count = db.execute(
            "SELECT COUNT(*) FROM face_registration_requests"
        ).fetchone()[0]
        db.execute(
            """
            CREATE TABLE face_registration_requests_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending', 'approved', 'rejected', 'cancelled')),
                request_type TEXT NOT NULL DEFAULT 'initial'
                    CHECK(request_type IN ('initial', 'update')),
                face_count_at_submit INTEGER NOT NULL DEFAULT 0,
                planned_remove_count INTEGER NOT NULL DEFAULT 0,
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
            )
            """
        )
        db.execute(
            f"""
            INSERT INTO face_registration_requests_new(
                id, student_id, status, request_type,
                face_count_at_submit, planned_remove_count,
                storage_key, front_image_path, left_image_path,
                right_image_path, up_image_path, down_image_path,
                note, reject_reason, reviewed_by, reviewed_at,
                created_at, updated_at
            )
            SELECT
                id, student_id, status, {request_type_expression},
                {face_count_expression}, {planned_remove_expression},
                storage_key, front_image_path, left_image_path,
                right_image_path, up_image_path, down_image_path,
                note, reject_reason, reviewed_by, reviewed_at,
                created_at, updated_at
            FROM face_registration_requests
            """
        )
        new_count = db.execute(
            "SELECT COUNT(*) FROM face_registration_requests_new"
        ).fetchone()[0]
        if new_count != old_count:
            raise RuntimeError(
                "Face request migration changed the number of records."
            )

        db.execute("DROP TABLE face_registration_requests")
        db.execute(
            """
            ALTER TABLE face_registration_requests_new
            RENAME TO face_registration_requests
            """
        )
        db.execute(
            """
            CREATE INDEX idx_face_registration_requests_student_created
            ON face_registration_requests(student_id, created_at DESC)
            """
        )
        db.execute(
            """
            CREATE INDEX idx_face_registration_requests_status_created
            ON face_registration_requests(status, created_at DESC)
            """
        )
        db.execute(
            """
            CREATE UNIQUE INDEX idx_face_registration_requests_one_pending
            ON face_registration_requests(student_id)
            WHERE status='pending'
            """
        )
        _record_migration(
            db, FACE_REQUEST_CONSTRAINTS_VERSION, migration_name
        )
        _raise_on_foreign_key_violations(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        _restore_foreign_keys(db)


def _prepare_rebuild(db: sqlite3.Connection) -> None:
    db.commit()
    db.execute("PRAGMA foreign_keys=OFF")
    if db.execute("PRAGMA foreign_keys").fetchone()[0] != 0:
        raise RuntimeError("Could not disable foreign keys for schema rebuild.")


def _restore_foreign_keys(db: sqlite3.Connection) -> None:
    db.execute("PRAGMA foreign_keys=ON")
    if db.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise RuntimeError("Could not restore foreign key enforcement.")


def _raise_on_foreign_key_violations(db: sqlite3.Connection) -> None:
    violations = db.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise RuntimeError(
            f"Schema migration produced {len(violations)} foreign key violation(s)."
        )

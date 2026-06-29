import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from app.core.config import settings
from app.core.security import hash_password


os.makedirs(os.path.dirname(settings.database_path), exist_ok=True)


@contextmanager
def get_db():
    conn = sqlite3.connect(settings.database_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as db:
        db.execute("PRAGMA journal_mode = WAL")
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'admin',
                student_id INTEGER,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_code TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                class_name TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS student_faces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                image_path TEXT,
                embedding TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS face_registration_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected', 'cancelled')),
                request_type TEXT NOT NULL DEFAULT 'initial' CHECK(request_type IN ('initial', 'update')),
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
            );

            CREATE TABLE IF NOT EXISTS student_attendance_settings (
                student_id INTEGER PRIMARY KEY,
                work_start_time TEXT NOT NULL,
                work_end_time TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS access_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                student_code TEXT,
                full_name TEXT,
                action TEXT NOT NULL,
                result TEXT NOT NULL,
                confidence REAL,
                note TEXT,
                evidence_image_path TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(student_id) REFERENCES students(id)
            );

            CREATE TABLE IF NOT EXISTS attendance_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                student_code TEXT,
                full_name TEXT,
                attendance_date TEXT NOT NULL,
                first_check_in_at TEXT,
                last_check_out_at TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                late_minutes INTEGER NOT NULL DEFAULT 0,
                early_leave_minutes INTEGER NOT NULL DEFAULT 0,
                total_minutes INTEGER NOT NULL DEFAULT 0,
                missing_checkout INTEGER NOT NULL DEFAULT 0,
                note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(student_id, attendance_date),
                FOREIGN KEY(student_id) REFERENCES students(id)
            );

            CREATE TABLE IF NOT EXISTS leave_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                leave_type TEXT NOT NULL CHECK(leave_type IN ('sick', 'personal', 'study', 'family', 'other')),
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                reason TEXT NOT NULL CHECK(length(trim(reason)) >= 5),
                status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected', 'cancelled', 'revoked')),
                reviewer_id INTEGER,
                reviewer_note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                approved_at TEXT,
                rejected_at TEXT,
                cancelled_at TEXT,
                revoked_at TEXT,
                CHECK(start_date <= end_date),
                FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE RESTRICT,
                FOREIGN KEY(reviewer_id) REFERENCES users(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS student_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                reviewer_id INTEGER NOT NULL,
                title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 3 AND 180),
                report_type TEXT NOT NULL CHECK(report_type IN ('weekly', 'monthly', 'project_progress', 'research', 'demo', 'other')),
                status TEXT NOT NULL DEFAULT 'submitted' CHECK(status IN ('submitted', 'revision_requested', 'approved')),
                current_version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE RESTRICT,
                FOREIGN KEY(reviewer_id) REFERENCES users(id) ON DELETE RESTRICT
            );

            CREATE TABLE IF NOT EXISTS student_report_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                version_no INTEGER NOT NULL,
                description TEXT,
                external_link TEXT,
                original_filename TEXT,
                storage_path TEXT,
                file_size INTEGER,
                media_type TEXT,
                submitted_by INTEGER NOT NULL,
                submitted_at TEXT NOT NULL,
                viewed_at TEXT,
                UNIQUE(report_id, version_no),
                CHECK(storage_path IS NOT NULL OR external_link IS NOT NULL),
                FOREIGN KEY(report_id) REFERENCES student_reports(id) ON DELETE CASCADE,
                FOREIGN KEY(submitted_by) REFERENCES users(id) ON DELETE RESTRICT
            );

            CREATE TABLE IF NOT EXISTS student_report_feedbacks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                version_id INTEGER NOT NULL,
                reviewer_id INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('revision_requested', 'approved')),
                comment TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(report_id) REFERENCES student_reports(id) ON DELETE CASCADE,
                FOREIGN KEY(version_id) REFERENCES student_report_versions(id) ON DELETE CASCADE,
                FOREIGN KEY(reviewer_id) REFERENCES users(id) ON DELETE RESTRICT
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'new',
                evidence_image_path TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS work_schedule_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                effective_from TEXT NOT NULL UNIQUE,
                monday_enabled INTEGER NOT NULL DEFAULT 1 CHECK(monday_enabled IN (0, 1)),
                tuesday_enabled INTEGER NOT NULL DEFAULT 1 CHECK(tuesday_enabled IN (0, 1)),
                wednesday_enabled INTEGER NOT NULL DEFAULT 1 CHECK(wednesday_enabled IN (0, 1)),
                thursday_enabled INTEGER NOT NULL DEFAULT 1 CHECK(thursday_enabled IN (0, 1)),
                friday_enabled INTEGER NOT NULL DEFAULT 1 CHECK(friday_enabled IN (0, 1)),
                saturday_enabled INTEGER NOT NULL DEFAULT 1 CHECK(saturday_enabled IN (0, 1)),
                sunday_enabled INTEGER NOT NULL DEFAULT 1 CHECK(sunday_enabled IN (0, 1)),
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                late_allowed_minutes INTEGER NOT NULL DEFAULT 5 CHECK(late_allowed_minutes >= 0),
                early_leave_allowed_minutes INTEGER NOT NULL DEFAULT 10 CHECK(early_leave_allowed_minutes >= 0),
                checkout_cutoff_time TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS work_calendar_exceptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exception_date TEXT NOT NULL UNIQUE,
                exception_type TEXT NOT NULL DEFAULT 'off' CHECK(exception_type IN ('off', 'working')),
                holiday_name TEXT NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
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
                created_at TEXT NOT NULL,
                FOREIGN KEY(actor_user_id) REFERENCES users(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS login_rate_limits (
                attempt_key TEXT PRIMARY KEY,
                failed_attempts INTEGER NOT NULL,
                first_failed_at INTEGER NOT NULL,
                locked_until INTEGER,
                updated_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_sessions (
                session_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                revoked_at INTEGER,
                ip_address TEXT,
                user_agent TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )
        _migrate_students_remove_contact_columns(db)
        user_columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(users)").fetchall()
        }
        if "student_id" not in user_columns:
            db.execute("ALTER TABLE users ADD COLUMN student_id INTEGER")
        if "status" not in user_columns:
            db.execute("ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
        face_request_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(face_registration_requests)").fetchall()
        }
        if "request_type" not in face_request_columns:
            db.execute("ALTER TABLE face_registration_requests ADD COLUMN request_type TEXT NOT NULL DEFAULT 'initial'")
        if "face_count_at_submit" not in face_request_columns:
            db.execute("ALTER TABLE face_registration_requests ADD COLUMN face_count_at_submit INTEGER NOT NULL DEFAULT 0")
        if "planned_remove_count" not in face_request_columns:
            db.execute("ALTER TABLE face_registration_requests ADD COLUMN planned_remove_count INTEGER NOT NULL DEFAULT 0")
        db.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_face_registration_requests_student_created ON face_registration_requests(student_id, created_at DESC)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_face_registration_requests_status_created ON face_registration_requests(status, created_at DESC)")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_face_registration_requests_one_pending ON face_registration_requests(student_id) WHERE status='pending'")
        db.execute("CREATE INDEX IF NOT EXISTS idx_leave_requests_student_dates ON leave_requests(student_id, status, start_date, end_date)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_leave_requests_status_dates ON leave_requests(status, start_date, end_date)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_student_reports_student_created ON student_reports(student_id, created_at DESC)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_student_reports_reviewer_status ON student_reports(reviewer_id, status, updated_at DESC)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_student_report_versions_report_version ON student_report_versions(report_id, version_no DESC)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_student_report_feedbacks_report_created ON student_report_feedbacks(report_id, created_at DESC)")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_student_id_unique ON users(student_id) WHERE student_id IS NOT NULL")
        db.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_expires_at ON user_sessions(expires_at)")
        access_log_columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(access_logs)").fetchall()
        }
        if "evidence_image_path" not in access_log_columns:
            db.execute("ALTER TABLE access_logs ADD COLUMN evidence_image_path TEXT")
        alert_columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(alerts)").fetchall()
        }
        if "evidence_image_path" not in alert_columns:
            db.execute("ALTER TABLE alerts ADD COLUMN evidence_image_path TEXT")
        if "event_date" not in alert_columns:
            db.execute("ALTER TABLE alerts ADD COLUMN event_date TEXT")
        _backfill_alert_event_dates(db)
        from app.services.private_storage import migrate_public_uploads_to_private

        migrate_public_uploads_to_private(db)
        attendance_columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(attendance_records)").fetchall()
        }
        if "missing_checkout_resolution" not in attendance_columns:
            db.execute("ALTER TABLE attendance_records ADD COLUMN missing_checkout_resolution TEXT")
        if "resolution_reason" not in attendance_columns:
            db.execute("ALTER TABLE attendance_records ADD COLUMN resolution_reason TEXT")
        if "resolution_checkout_at" not in attendance_columns:
            db.execute("ALTER TABLE attendance_records ADD COLUMN resolution_checkout_at TEXT")
        if "force_zero_minutes" not in attendance_columns:
            db.execute("ALTER TABLE attendance_records ADD COLUMN force_zero_minutes INTEGER NOT NULL DEFAULT 0")
        db.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_entity_type ON audit_logs(entity_type)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_username ON audit_logs(actor_username)")
        admin = db.execute("SELECT id FROM users WHERE username = ?", (settings.default_admin_username,)).fetchone()
        if not admin:
            db.execute(
                "INSERT INTO users(username, password_hash, role, created_at) VALUES (?, ?, 'admin', ?)",
                (settings.default_admin_username, hash_password(settings.default_admin_password), datetime.now().isoformat(timespec="seconds")),
            )
        default_settings = {
            "face_threshold": str(settings.face_threshold),
            "check_cooldown_seconds": str(settings.check_cooldown_seconds),
            "frame_skip": str(settings.frame_skip),
            "camera_mode": "check_in",
            "check_in_camera_device_id": settings.check_in_camera_device_id,
            "check_out_camera_device_id": settings.check_out_camera_device_id,
            "auto_start_cameras": "true" if settings.auto_start_cameras else "false",
            "check_in_camera_source": settings.check_in_camera_source,
            "check_out_camera_source": settings.check_out_camera_source,
            "liveness_enabled": "true" if settings.liveness_enabled else "false",
            "liveness_threshold": str(settings.liveness_threshold),
            "liveness_real_class_index": str(settings.liveness_real_class_index),
            "liveness_crop_scale": str(settings.liveness_crop_scale),
            "liveness_min_face_size": str(settings.liveness_min_face_size),
            "liveness_min_brightness": str(settings.liveness_min_brightness),
            "liveness_min_blur": str(settings.liveness_min_blur),
            "liveness_edge_margin": str(settings.liveness_edge_margin),
            "missing_checkout_cutoff_time": settings.missing_checkout_cutoff_time,
            "missing_checkout_scan_interval_seconds": str(settings.missing_checkout_scan_interval_seconds),
            "work_start_time": settings.work_start_time,
            "work_end_time": settings.work_end_time,
            "late_grace_minutes": str(settings.late_grace_minutes),
            "early_leave_grace_minutes": str(settings.early_leave_grace_minutes),
        }
        for key, value in default_settings.items():
            db.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value))
        db.execute(
            """
            INSERT OR IGNORE INTO work_schedule_settings(
                effective_from, monday_enabled, tuesday_enabled, wednesday_enabled,
                thursday_enabled, friday_enabled, saturday_enabled, sunday_enabled,
                start_time, end_time, late_allowed_minutes, early_leave_allowed_minutes,
                checkout_cutoff_time, updated_at
            ) VALUES (?, 1, 1, 1, 1, 1, 1, 1, ?, ?, ?, ?, ?, ?)
            """,
            (
                "1970-01-01", settings.work_start_time, settings.work_end_time,
                settings.late_grace_minutes, settings.early_leave_grace_minutes,
                settings.missing_checkout_cutoff_time, datetime.now().isoformat(timespec="seconds"),
            ),
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_work_schedule_effective_from ON work_schedule_settings(effective_from)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_work_calendar_exception_date ON work_calendar_exceptions(exception_date)")


def _backfill_alert_event_dates(db):
    rows = db.execute(
        "SELECT id, message, created_at FROM alerts WHERE event_date IS NULL OR event_date=''"
    ).fetchall()
    for row in rows:
        event_date = None
        match = re.search(r"ngày\s+(\d{2})/(\d{2})/(\d{4})", row["message"] or "", re.IGNORECASE)
        if match:
            day, month, year = match.groups()
            event_date = f"{year}-{month}-{day}"
        elif row["created_at"]:
            event_date = row["created_at"][:10]
        if event_date:
            db.execute("UPDATE alerts SET event_date=? WHERE id=?", (event_date, row["id"]))


def _migrate_students_remove_contact_columns(db):
    student_columns = {
        row["name"]
        for row in db.execute("PRAGMA table_info(students)").fetchall()
    }
    if "email" not in student_columns and "phone" not in student_columns:
        return

    db.execute("PRAGMA foreign_keys=OFF")
    db.executescript(
        """
        DROP TABLE IF EXISTS students_without_contact;
        CREATE TABLE students_without_contact (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_code TEXT NOT NULL UNIQUE,
            full_name TEXT NOT NULL,
            class_name TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL
        );
        INSERT INTO students_without_contact(id, student_code, full_name, class_name, status, created_at)
        SELECT id, student_code, full_name, class_name, status, created_at
        FROM students;
        DROP TABLE students;
        ALTER TABLE students_without_contact RENAME TO students;
        """
    )
    db.execute("PRAGMA foreign_keys=ON")


def row_to_dict(row):
    return dict(row) if row is not None else None


def get_setting(key: str, default=None):
    with get_db() as db:
        row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str):
    with get_db() as db:
        db.execute("INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

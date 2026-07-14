import json
import tempfile
import unittest
from datetime import datetime
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile


class AttendanceExportApiTests(unittest.TestCase):
    def setUp(self):
        try:
            from fastapi.testclient import TestClient
            from app import db as db_module
            from app.core import security
            from app.main import app
        except ModuleNotFoundError as exc:
            self.skipTest(f"{exc.name} is not installed in this test environment.")

        self.TestClient = TestClient
        self.db_module = db_module
        self.security = security
        self.app = app
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_database_path = db_module.settings.database_path
        self.original_iterations = security.settings.password_pbkdf2_iterations
        self.original_admin_username = db_module.settings.default_admin_username
        self.original_admin_password = db_module.settings.default_admin_password
        db_module.settings.database_path = str(Path(self.temp_dir.name) / "attendance_export.db")
        db_module.settings.password_pbkdf2_iterations = 1_000
        db_module.settings.default_admin_username = "admin"
        db_module.settings.default_admin_password = "admin123"
        db_module.init_db()
        self._seed_data()

    def tearDown(self):
        if hasattr(self, "db_module"):
            self.db_module.settings.database_path = self.original_database_path
            self.db_module.settings.password_pbkdf2_iterations = self.original_iterations
            self.db_module.settings.default_admin_username = self.original_admin_username
            self.db_module.settings.default_admin_password = self.original_admin_password
        if hasattr(self, "temp_dir"):
            self.temp_dir.cleanup()

    def _seed_data(self):
        with self.db_module.get_db() as db:
            now = datetime.now().isoformat(timespec="seconds")
            db.executemany(
                "INSERT INTO students(student_code, full_name, class_name, status, created_at) VALUES (?, ?, ?, 'active', ?)",
                [
                    ("SV001", "Nguyễn Văn An", "CNTT-K15", now),
                    ("SV002", "=HYPERLINK(\"https://invalid\",\"x\")", "ATTT-K15", now),
                ],
            )
            students = db.execute("SELECT id, student_code FROM students ORDER BY id").fetchall()
            ids = {row["student_code"]: row["id"] for row in students}
            db.executemany(
                """
                INSERT INTO attendance_records(
                    student_id, student_code, full_name, attendance_date,
                    first_check_in_at, last_check_out_at, status, late_minutes,
                    early_leave_minutes, total_minutes, missing_checkout, note, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (ids["SV001"], "SV001", "Nguyễn Văn An", "2026-07-01", "2026-07-01T08:00:00", "2026-07-01T17:00:00", "present_on_time", 0, 0, 540, 0, "Đủ giờ", now, now),
                    (ids["SV001"], "SV001", "Nguyễn Văn An", "2026-07-02", "2026-07-02T08:17:00", "2026-07-02T16:45:00", "late_and_early_leave", 12, 5, 508, 0, "+SUM(1,1)", now, now),
                    (ids["SV002"], "SV002", "=HYPERLINK(\"https://invalid\",\"x\")", "2026-07-01", "2026-07-01T08:05:00", None, "missing_checkout", 0, 0, 0, 1, "Thiếu giờ ra", now, now),
                ],
            )
            password_hash = self.security.hash_password("manager123")
            db.execute(
                "INSERT INTO users(username, password_hash, role, status, created_at) VALUES (?, ?, 'lab_manager', 'active', ?)",
                ("manager", password_hash, now),
            )
            db.execute(
                "INSERT INTO users(username, password_hash, role, student_id, status, created_at) VALUES (?, ?, 'student', ?, 'active', ?)",
                ("student", self.security.hash_password("student123"), ids["SV001"], now),
            )

    def client(self):
        return self.TestClient(self.app, base_url="http://127.0.0.1")

    def login(self, client, username="admin", password="admin123"):
        response = client.post("/api/auth/login", json={"username": username, "password": password})
        self.assertEqual(response.status_code, 200, response.text)

    def csrf_headers(self, client):
        return {"X-CSRF-Token": client.cookies.get("csrf_token", "")}

    def payload(self, **overrides):
        payload = {
            "date_from": "2026-07-01",
            "date_to": "2026-07-31",
            "status": None,
            "q": None,
            "include_summary": True,
            "include_details": True,
        }
        payload.update(overrides)
        return payload

    def post_export(self, client, payload=None):
        return client.post(
            "/api/exports/attendance",
            json=payload or self.payload(),
            headers=self.csrf_headers(client),
        )

    def workbook_parts(self, response):
        archive = ZipFile(BytesIO(response.content))
        self.assertIsNone(archive.testzip())
        return archive, {name: archive.read(name).decode("utf-8") for name in archive.namelist() if name.endswith(".xml")}

    def test_admin_export_has_two_sheets_headers_styles_formulas_and_audit(self):
        client = self.client()
        self.login(client)
        response = self.post_export(client)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", response.headers["content-type"])
        self.assertIn("bao_cao_cham_cong_2026-07-01_2026-07-31.xlsx", response.headers["content-disposition"])

        archive, parts = self.workbook_parts(response)
        self.assertIn("xl/worksheets/sheet1.xml", archive.namelist())
        self.assertIn("xl/worksheets/sheet2.xml", archive.namelist())
        self.assertIn('name="Tong_hop"', parts["xl/workbook.xml"])
        self.assertIn('name="Chi_tiet"', parts["xl/workbook.xml"])
        self.assertIn("Nguyễn Văn An", parts["xl/worksheets/sheet2.xml"])
        self.assertIn("Tỷ lệ hiện diện", parts["xl/worksheets/sheet1.xml"])
        self.assertIn("<f>IF(F8=0,0,G8/F8)</f>", parts["xl/worksheets/sheet1.xml"])
        self.assertIn("'", parts["xl/worksheets/sheet2.xml"])
        self.assertNotIn("embedding", response.content.decode("utf-8", errors="ignore").lower())
        self.assertNotIn("evidence_image_path", response.content.decode("utf-8", errors="ignore").lower())

        audit = client.get("/api/audit-logs?entity_type=attendance_export")
        self.assertEqual(audit.status_code, 200, audit.text)
        item = audit.json()["items"][0]
        self.assertEqual(item["action"], "attendance.export_xlsx")
        self.assertEqual(json.loads(item["details_json"])["row_count"], 3)

    def test_auth_csrf_roles_and_manager_access(self):
        anonymous = self.client()
        self.assertEqual(anonymous.post("/api/exports/attendance", json=self.payload()).status_code, 401)

        admin = self.client()
        self.login(admin)
        self.assertEqual(admin.post("/api/exports/attendance", json=self.payload()).status_code, 403)

        student = self.client()
        self.login(student, "student", "student123")
        self.assertEqual(self.post_export(student).status_code, 403)

        manager = self.client()
        self.login(manager, "manager", "manager123")
        self.assertEqual(self.post_export(manager).status_code, 200)

    def test_validation_and_filters(self):
        client = self.client()
        self.login(client)
        invalid_payloads = [
            self.payload(date_from="2026-07-10", date_to="2026-07-01"),
            self.payload(date_from="2025-01-01", date_to="2026-01-02"),
            self.payload(status="not-a-status"),
            self.payload(include_summary=False, include_details=False),
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                self.assertEqual(self.post_export(client, payload).status_code, 422)

        filtered = self.post_export(
            client,
            self.payload(q="SV001", status="present_on_time", include_summary=False),
        )
        self.assertEqual(filtered.status_code, 200, filtered.text)
        _, parts = self.workbook_parts(filtered)
        detail = parts["xl/worksheets/sheet1.xml"]
        self.assertIn("Nguyễn Văn An", detail)
        self.assertNotIn("HYPERLINK", detail)
        self.assertIn('ref="A1:N8"', detail)

    def test_export_is_not_silently_truncated_at_one_thousand_rows(self):
        now = datetime.now().isoformat(timespec="seconds")
        with self.db_module.get_db() as db:
            students = [(f"B{index:04d}", f"Bulk Student {index}", "BULK", now) for index in range(1005)]
            db.executemany(
                "INSERT INTO students(student_code, full_name, class_name, status, created_at) VALUES (?, ?, ?, 'active', ?)",
                students,
            )
            rows = db.execute("SELECT id, student_code, full_name FROM students WHERE class_name='BULK'").fetchall()
            db.executemany(
                """
                INSERT INTO attendance_records(
                    student_id, student_code, full_name, attendance_date, status,
                    late_minutes, early_leave_minutes, total_minutes, missing_checkout,
                    note, created_at, updated_at
                ) VALUES (?, ?, ?, '2026-07-03', 'present_on_time', 0, 0, 480, 0, NULL, ?, ?)
                """,
                [(row["id"], row["student_code"], row["full_name"], now, now) for row in rows],
            )

        client = self.client()
        self.login(client)
        response = self.post_export(
            client,
            self.payload(q="Bulk Student", include_summary=False, include_details=True),
        )
        self.assertEqual(response.status_code, 200, response.text)
        _, parts = self.workbook_parts(response)
        self.assertIn('ref="A1:N1012"', parts["xl/worksheets/sheet1.xml"])


class AttendanceExportServiceTests(unittest.TestCase):
    def test_row_limit_is_rejected_instead_of_truncated(self):
        from app.repositories.attendance_export_repository import MAX_EXPORT_ROWS
        from app.schemas.exports import AttendanceExportRequest
        from app.services.attendance_export_service import ExportRowLimitError, build_attendance_workbook

        sample = {
            "id": 1,
            "student_id": 1,
            "student_code": "SV001",
            "full_name": "A",
            "class_name": "C",
            "attendance_date": "2026-07-01",
            "first_check_in_at": None,
            "last_check_out_at": None,
            "status": "pending",
            "late_minutes": 0,
            "early_leave_minutes": 0,
            "total_minutes": 0,
            "missing_checkout": 0,
            "note": None,
        }
        rows = [sample] * (MAX_EXPORT_ROWS + 1)
        payload = AttendanceExportRequest(date_from="2026-07-01", date_to="2026-07-01")
        with self.assertRaises(ExportRowLimitError):
            build_attendance_workbook(rows, payload, {"username": "admin", "role": "admin"})


class AttendanceExportDashboardContractTests(unittest.TestCase):
    def test_export_defaults_to_all_students_and_has_no_class_filter(self):
        project_root = Path(__file__).resolve().parents[1]
        template = (project_root / "web" / "templates" / "dashboard.html").read_text(encoding="utf-8")
        script = (project_root / "web" / "static" / "js" / "app-exports.js").read_text(encoding="utf-8")

        self.assertNotIn("exportAttendanceClass", template)
        self.assertNotIn("attendanceClassFilter", template)
        self.assertIn("Chỉ xuất sinh viên (không bắt buộc)", template)
        self.assertIn("setInputValue('exportAttendanceQuery', '');", script)
        self.assertNotIn("copyAttendanceExportFilter('attendanceSearch'", script)
        self.assertNotIn("class_name", script)


if __name__ == "__main__":
    unittest.main()

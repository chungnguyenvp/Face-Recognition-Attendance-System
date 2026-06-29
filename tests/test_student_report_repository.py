import sqlite3
import unittest

from app.repositories import student_report_repository as reports


class StudentReportRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL
            );
            CREATE TABLE students (
                id INTEGER PRIMARY KEY,
                student_code TEXT NOT NULL,
                full_name TEXT NOT NULL
            );
            CREATE TABLE student_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                reviewer_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                report_type TEXT NOT NULL,
                status TEXT NOT NULL,
                current_version INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE student_report_versions (
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
                viewed_at TEXT
            );
            CREATE TABLE student_report_feedbacks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                version_id INTEGER NOT NULL,
                reviewer_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                comment TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        self.db.executemany(
            "INSERT INTO users(id, username, role, status) VALUES (?, ?, ?, ?)",
            [
                (1, "student-one", "student", "active"),
                (2, "manager-one", "lab_manager", "active"),
                (3, "manager-two", "lab_manager", "active"),
                (4, "locked-manager", "lab_manager", "inactive"),
            ],
        )
        self.db.executemany(
            "INSERT INTO students(id, student_code, full_name) VALUES (?, ?, ?)",
            [(1, "SV001", "Student One"), (2, "SV002", "Student Two")],
        )

    def tearDown(self):
        self.db.close()

    def _new_report(self, student_id=1, reviewer_id=2, title="Bao cao tuan", created_at="2026-06-23T10:00:00"):
        report_id = reports.create_report(
            self.db, student_id, reviewer_id, title, "weekly", created_at
        )
        version_id = reports.create_version(
            self.db, report_id, 1, "Noi dung", None, "bao_cao.pdf", f"student_reports/report_{report_id}/version_1/file.pdf",
            12, "application/pdf", 1, created_at,
        )
        return report_id, version_id

    def test_lists_only_active_lab_managers(self):
        managers = reports.list_active_lab_managers(self.db)
        self.assertEqual([(item["id"], item["username"]) for item in managers], [(2, "manager-one"), (3, "manager-two")])

    def test_student_and_lab_manager_lists_are_scoped_to_owner_and_reviewer(self):
        first_id, first_version = self._new_report()
        second_id, _ = self._new_report(student_id=2, reviewer_id=3, title="Bao cao khac", created_at="2026-06-23T11:00:00")
        reports.create_feedback(self.db, first_id, first_version, 2, "revision_requested", "Bo sung ket qua test.", "2026-06-23T12:00:00")

        student_items = reports.list_reports_for_student(self.db, 1, 20)
        first_manager_items = reports.list_reports_for_staff(self.db, 2, 20, None, None, None)
        second_manager_items = reports.list_reports_for_staff(self.db, 3, 20, None, None, None)
        admin_items = reports.list_reports_for_staff(self.db, None, 20, None, None, None)

        self.assertEqual([item["id"] for item in student_items], [first_id])
        self.assertEqual(student_items[0]["feedback_count"], 1)
        self.assertEqual([item["id"] for item in first_manager_items], [first_id])
        self.assertEqual([item["id"] for item in second_manager_items], [second_id])
        self.assertEqual({item["id"] for item in admin_items}, {first_id, second_id})
        self.assertIsNone(first_manager_items[0]["current_viewed_at"])

    def test_transitions_require_the_expected_current_status_and_keep_version_history(self):
        report_id, first_version = self._new_report()
        self.assertTrue(reports.update_review_status(self.db, report_id, "revision_requested", "2026-06-23T12:00:00"))
        self.assertFalse(reports.update_review_status(self.db, report_id, "approved", "2026-06-23T12:01:00"))
        self.assertTrue(reports.update_for_resubmission(self.db, report_id, 2, "2026-06-23T13:00:00"))
        second_version = reports.create_version(
            self.db, report_id, 2, "Da sua", None, "bao_cao_v2.pdf", "student_reports/report_1/version_2/file.pdf",
            24, "application/pdf", 1, "2026-06-23T13:00:00",
        )
        reports.mark_current_version_viewed(self.db, report_id, "2026-06-23T14:00:00")

        report = reports.get_report(self.db, report_id)
        versions = reports.list_versions(self.db, report_id)
        self.assertEqual(report["status"], "submitted")
        self.assertEqual(report["current_version"], 2)
        self.assertEqual(report["current_version_id"], second_version)
        self.assertEqual(report["current_viewed_at"], "2026-06-23T14:00:00")
        self.assertEqual([item["id"] for item in versions], [second_version, first_version])
        self.assertFalse(reports.update_for_resubmission(self.db, report_id, 3, "2026-06-23T15:00:00"))


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from app.services import private_storage


class ReportPrivateStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_root = private_storage.PRIVATE_STORAGE_ROOT
        self.original_report_dir = private_storage.PRIVATE_REPORT_DIR
        private_storage.PRIVATE_STORAGE_ROOT = Path(self.temp_dir.name) / "private"
        private_storage.PRIVATE_REPORT_DIR = private_storage.PRIVATE_STORAGE_ROOT / "student_reports"

    def tearDown(self):
        private_storage.PRIVATE_STORAGE_ROOT = self.original_root
        private_storage.PRIVATE_REPORT_DIR = self.original_report_dir
        self.temp_dir.cleanup()

    def test_report_file_resolves_only_inside_private_report_root(self):
        relative_path = private_storage.report_relative_path(12, 3, "stored-file.pdf")
        target = private_storage.private_disk_path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"%PDF-1.4\nreport")

        self.assertEqual(relative_path, "student_reports/report_12/version_3/stored-file.pdf")
        self.assertEqual(private_storage.resolve_private_file(relative_path, "report"), target)
        self.assertEqual(private_storage.resolve_private_file(f"storage/private/{relative_path}", "report"), target)

    def test_report_paths_reject_wrong_prefix_and_path_traversal(self):
        self.assertIsNone(private_storage.normalize_private_path("faces/face.jpg", "report"))
        self.assertIsNone(private_storage.normalize_private_path("student_reports/../../settings.env", "report"))
        self.assertIsNone(private_storage.resolve_private_file("student_reports/../../settings.env", "report"))
        with self.assertRaises(ValueError):
            private_storage.private_disk_path("student_reports/../../settings.env")


if __name__ == "__main__":
    unittest.main()

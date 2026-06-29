import sqlite3
import unittest

from app.repositories import private_storage_repository


class PrivateStorageRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
            CREATE TABLE student_faces (id INTEGER PRIMARY KEY, image_path TEXT);
            CREATE TABLE access_logs (id INTEGER PRIMARY KEY, evidence_image_path TEXT);
            CREATE TABLE alerts (id INTEGER PRIMARY KEY, evidence_image_path TEXT);
            """
        )
        self.db.execute("INSERT INTO student_faces(id, image_path) VALUES (1, '/static/uploads/faces/face.jpg')")
        self.db.execute("INSERT INTO access_logs(id, evidence_image_path) VALUES (1, 'web/static/uploads/evidence/log.jpg')")
        self.db.execute("INSERT INTO alerts(id, evidence_image_path) VALUES (1, 'storage/private/evidence/alert.jpg')")

    def tearDown(self):
        self.db.close()

    def test_lists_and_updates_legacy_storage_paths(self):
        faces = private_storage_repository.list_legacy_student_faces(self.db)
        access_logs = private_storage_repository.list_legacy_evidence_paths(self.db, "access_logs")
        alerts = private_storage_repository.list_legacy_evidence_paths(self.db, "alerts")

        self.assertEqual([row["id"] for row in faces], [1])
        self.assertEqual([row["id"] for row in access_logs], [1])
        self.assertEqual([row["id"] for row in alerts], [1])

        private_storage_repository.update_student_face_path(self.db, 1, "faces/face.jpg")
        private_storage_repository.update_evidence_path(self.db, "access_logs", 1, "evidence/log.jpg")

        self.assertEqual(self.db.execute("SELECT image_path FROM student_faces WHERE id=1").fetchone()["image_path"], "faces/face.jpg")
        self.assertEqual(
            self.db.execute("SELECT evidence_image_path FROM access_logs WHERE id=1").fetchone()["evidence_image_path"],
            "evidence/log.jpg",
        )

    def test_rejects_unsupported_evidence_table(self):
        with self.assertRaises(ValueError):
            private_storage_repository.list_legacy_evidence_paths(self.db, "students")

        with self.assertRaises(ValueError):
            private_storage_repository.update_evidence_path(self.db, "students", 1, "evidence/file.jpg")


if __name__ == "__main__":
    unittest.main()

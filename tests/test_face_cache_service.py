import unittest

from app.services.face_cache_service import FaceEmbeddingCache


class FaceEmbeddingCacheTests(unittest.TestCase):
    def test_cache_loads_once_until_invalidated(self):
        cache = FaceEmbeddingCache()
        calls = []

        def loader():
            calls.append(1)
            return [{"student_id": len(calls)}]

        first = cache.get_known_faces(loader)
        second = cache.get_known_faces(loader)

        self.assertIs(first, second)
        self.assertEqual(len(calls), 1)
        self.assertEqual(second[0]["student_id"], 1)

        cache.invalidate()
        third = cache.get_known_faces(loader)

        self.assertEqual(len(calls), 2)
        self.assertEqual(third[0]["student_id"], 2)


if __name__ == "__main__":
    unittest.main()

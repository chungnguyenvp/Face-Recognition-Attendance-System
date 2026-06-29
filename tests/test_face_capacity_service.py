import unittest

from app.services.face_capacity_service import MAX_FACE_SAMPLES, plan_face_update


class FaceCapacityServiceTests(unittest.TestCase):
    def test_five_new_faces_fit_without_removing_when_below_capacity(self):
        plan = plan_face_update(4)

        self.assertEqual(plan.removed_face_count, 0)
        self.assertEqual(plan.face_count_after, 9)

    def test_five_new_faces_replace_only_three_oldest_faces_from_eight(self):
        plan = plan_face_update(8)

        self.assertEqual(plan.removed_face_count, 3)
        self.assertEqual(plan.face_count_after, MAX_FACE_SAMPLES)

    def test_five_new_faces_replace_five_oldest_faces_at_capacity(self):
        plan = plan_face_update(MAX_FACE_SAMPLES)

        self.assertEqual(plan.removed_face_count, 5)
        self.assertEqual(plan.face_count_after, MAX_FACE_SAMPLES)

    def test_negative_counts_are_rejected(self):
        with self.assertRaises(ValueError):
            plan_face_update(-1)


if __name__ == "__main__":
    unittest.main()

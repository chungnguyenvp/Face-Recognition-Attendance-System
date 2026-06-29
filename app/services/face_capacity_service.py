from dataclasses import dataclass


MAX_FACE_SAMPLES = 10


@dataclass(frozen=True)
class FaceUpdatePlan:
    face_count_before: int
    incoming_face_count: int
    removed_face_count: int
    face_count_after: int


def plan_face_update(face_count_before: int, incoming_face_count: int = 5) -> FaceUpdatePlan:
    if face_count_before < 0 or incoming_face_count < 0:
        raise ValueError("So mau khuon mat khong hop le.")

    removed_face_count = max(0, face_count_before + incoming_face_count - MAX_FACE_SAMPLES)
    return FaceUpdatePlan(
        face_count_before=face_count_before,
        incoming_face_count=incoming_face_count,
        removed_face_count=removed_face_count,
        face_count_after=face_count_before - removed_face_count + incoming_face_count,
    )

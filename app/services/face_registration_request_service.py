from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.ai.face_engine import face_service
from app.repositories import face_registration_request_repository, student_face_repository
from app.services.audit_service import write_audit_log
from app.services.private_storage import face_request_relative_path, private_disk_path, resolve_private_file
from app.services.student_face_service import (
    delete_face_image_files,
    duplicate_warnings,
    raise_if_duplicate_face,
    save_face_image,
)
from app.services.face_capacity_service import FaceUpdatePlan, plan_face_update


FACE_REQUEST_POSITIONS = ("front", "left", "right", "up", "down")


@dataclass(frozen=True)
class ApprovalResult:
    item: dict
    replaced_image_paths: list[str]
    face_count_before: int
    removed_face_count: int
    face_count_after: int


def face_update_plan(face_count: int, incoming_count: int = len(FACE_REQUEST_POSITIONS)) -> FaceUpdatePlan:
    return plan_face_update(face_count, incoming_count)


def planned_remove_count(face_count: int, incoming_count: int = len(FACE_REQUEST_POSITIONS)) -> int:
    return face_update_plan(face_count, incoming_count).removed_face_count


def submit_request(db, student: dict, actor: dict, prepared_images: list[dict], note: str | None, request) -> dict:
    if student["status"] != "active":
        raise ValueError("Khong the dang ky FaceID cho sinh vien inactive.")
    if len(prepared_images) != len(FACE_REQUEST_POSITIONS):
        raise ValueError("Can chup du 5 anh khuon mat.")
    if face_registration_request_repository.get_pending_request_by_student(db, student["id"]):
        raise ValueError("Ban da co yeu cau FaceID dang cho duyet.")

    face_count = student_face_repository.count_student_faces(db, student["id"])
    request_type = "initial" if face_count == 0 else "update"
    capacity = face_update_plan(face_count)
    storage_key, image_paths = save_request_images(prepared_images)
    now_text = _now()
    try:
        request_id = face_registration_request_repository.create_request(
            db,
            student["id"],
            request_type,
            face_count,
            capacity.removed_face_count,
            storage_key,
            image_paths,
            note,
            now_text,
        )
        write_audit_log(
            db,
            actor,
            "face_requests.submit",
            "face_registration_request",
            request_id,
            f"{student['student_code']} - {student['full_name']}",
            {
                "student_id": student["id"],
                "request_type": request_type,
                "image_count": len(prepared_images),
                "face_count_at_submit": face_count,
                "planned_remove_count": capacity.removed_face_count,
            },
            request,
        )
    except Exception:
        delete_request_images(image_paths.values())
        raise
    return dict(face_registration_request_repository.get_request_by_id(db, request_id))


def approve_request(db, request_id: int, reviewer: dict, request) -> ApprovalResult:
    item = face_registration_request_repository.get_request_by_id(db, request_id)
    if not item:
        raise LookupError("Khong tim thay yeu cau FaceID.")
    if item["status"] != "pending":
        raise ValueError("Yeu cau nay da duoc xu ly.")
    prepared_images = _prepare_requested_images(item)
    duplicates = duplicate_warnings(db, item["student_id"], [image["embedding"] for image in prepared_images])
    raise_if_duplicate_face(duplicates)

    face_count_before = student_face_repository.count_student_faces(db, item["student_id"])
    capacity = face_update_plan(face_count_before, len(prepared_images))
    old_faces = student_face_repository.list_oldest_student_faces(
        db, item["student_id"], capacity.removed_face_count
    )
    old_face_ids = [face["id"] for face in old_faces]
    old_image_paths = [face["image_path"] for face in old_faces if face["image_path"]]
    saved = []
    now_text = _now()
    try:
        for image in prepared_images:
            saved.append(
                {
                    "image_path": save_face_image(item, image["data"]),
                    "embedding": face_service.serialize_embedding(image["embedding"]),
                }
            )
        for saved_item in saved:
            student_face_repository.create_student_face(
                db, item["student_id"], saved_item["image_path"], saved_item["embedding"], now_text
            )
        student_face_repository.delete_student_faces_by_ids(db, old_face_ids)
        if not face_registration_request_repository.mark_approved(db, request_id, reviewer["id"], now_text):
            raise ValueError("Yeu cau nay vua duoc xu ly boi nguoi khac.")
        write_audit_log(
            db,
            reviewer,
            "face_requests.approve",
            "face_registration_request",
            request_id,
            f"{item['student_code']} - {item['full_name']}",
            {
                "student_id": item["student_id"],
                "request_type": item["request_type"],
                "image_count": len(saved),
                "face_count_before": face_count_before,
                "removed_face_count": capacity.removed_face_count,
                "face_count_after": capacity.face_count_after,
                "duplicate_warnings": duplicates,
            },
            request,
        )
    except Exception:
        delete_face_image_files([saved_item["image_path"] for saved_item in saved])
        raise
    return ApprovalResult(
        item=dict(face_registration_request_repository.get_request_by_id(db, request_id)),
        replaced_image_paths=old_image_paths,
        face_count_before=face_count_before,
        removed_face_count=capacity.removed_face_count,
        face_count_after=capacity.face_count_after,
    )


def reject_request(db, request_id: int, reviewer: dict, reason: str, request) -> dict:
    item = face_registration_request_repository.get_request_by_id(db, request_id)
    if not item:
        raise LookupError("Khong tim thay yeu cau FaceID.")
    if item["status"] != "pending":
        raise ValueError("Yeu cau nay da duoc xu ly.")
    if not face_registration_request_repository.mark_rejected(db, request_id, reviewer["id"], reason, _now()):
        raise ValueError("Yeu cau nay vua duoc xu ly boi nguoi khac.")
    write_audit_log(
        db,
        reviewer,
        "face_requests.reject",
        "face_registration_request",
        request_id,
        f"{item['student_code']} - {item['full_name']}",
        {
            "student_id": item["student_id"],
            "request_type": item["request_type"],
            "reason": reason,
        },
        request,
    )
    return dict(face_registration_request_repository.get_request_by_id(db, request_id))


def cancel_request(db, request_id: int, student: dict, actor: dict, request) -> dict:
    item = face_registration_request_repository.get_request_by_id(db, request_id)
    if not item or item["student_id"] != student["id"]:
        raise LookupError("Khong tim thay yeu cau FaceID.")
    if not face_registration_request_repository.cancel_pending_request(db, request_id, student["id"], _now()):
        raise ValueError("Yeu cau nay da duoc xu ly, khong the huy.")
    write_audit_log(
        db,
        actor,
        "face_requests.cancel",
        "face_registration_request",
        request_id,
        f"{student['student_code']} - {student['full_name']}",
        {"student_id": student["id"], "request_type": item["request_type"]},
        request,
    )
    return dict(face_registration_request_repository.get_request_by_id(db, request_id))


def save_request_images(prepared_images: list[dict]) -> tuple[str, dict[str, str]]:
    storage_key = uuid4().hex
    image_paths = {}
    try:
        for position, image in zip(FACE_REQUEST_POSITIONS, prepared_images, strict=True):
            relative_path = face_request_relative_path(storage_key, f"{position}.jpg")
            path = private_disk_path(relative_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(image["data"])
            image_paths[position] = relative_path
    except Exception:
        delete_request_images(image_paths.values())
        raise
    return storage_key, image_paths


def delete_request_images(image_paths) -> None:
    for image_path in image_paths:
        path = resolve_private_file(image_path, "face_request")
        if not path:
            continue
        try:
            path.unlink()
        except OSError:
            pass


def request_image_path(item, position: str) -> Path | None:
    if position not in FACE_REQUEST_POSITIONS:
        return None
    return resolve_private_file(item[f"{position}_image_path"], "face_request")


def request_image_paths(item) -> list[str]:
    return [item[f"{position}_image_path"] for position in FACE_REQUEST_POSITIONS]


def _prepare_requested_images(item) -> list[dict]:
    prepared = []
    for position in FACE_REQUEST_POSITIONS:
        path = request_image_path(item, position)
        if not path:
            raise ValueError("Khong tim thay anh trong yeu cau FaceID.")
        from app.services.student_face_service import prepare_face_upload

        prepared.append(prepare_face_upload(path.read_bytes(), f"Anh {position}"))
    return prepared


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from app.ai.embedding_cache import face_embedding_cache
from app.ai.face_engine import face_service
from app.db import get_db
from app.repositories import student_face_repository, student_repository
from app.routers.deps import require_admin_or_lab_manager
from app.schemas.students import FaceAnalyzeRequest
from app.services.audit_service import write_audit_log
from app.services.student_face_service import (
    FACE_SCAN_REQUIRED_FILES,
    MAX_FACE_EMBEDDINGS_PER_STUDENT,
    delete_face_image_files as _delete_face_image_files,
    duplicate_warnings as _duplicate_warnings,
    prepare_face_upload as _prepare_face_upload,
    raise_if_duplicate_face as _raise_if_duplicate_face,
    read_limited_image_upload as _read_limited_image_upload,
    save_face_image as _save_face_image,
    trim_old_face_embeddings as _trim_old_face_embeddings,
)

router = APIRouter(prefix="/api/students", tags=["student_faces"])


def _get_student_or_404(student_id: int):
    with get_db() as db:
        student = student_repository.get_student_by_id(db, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Không tìm thấy sinh viên.")
    return student


@router.post("/face-scan/analyze", dependencies=[Depends(require_admin_or_lab_manager)])
def analyze_face_scan(payload: FaceAnalyzeRequest):
    try:
        image = face_service.read_image_from_base64(payload.image)
        return face_service.analyze_single_face_pose(image)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{student_id}/faces/upload")
async def upload_face(student_id: int, request: Request, file: UploadFile = File(...), actor=Depends(require_admin_or_lab_manager)):
    student = _get_student_or_404(student_id)
    if student["status"] != "active":
        raise HTTPException(status_code=400, detail="Không thể đăng ký khuôn mặt cho sinh viên inactive.")
    data = await _read_limited_image_upload(file, "Ảnh")
    prepared = _prepare_face_upload(data, "Ảnh")

    image_path = _save_face_image(student, prepared["data"])
    embedding_text = face_service.serialize_embedding(prepared["embedding"])
    try:
        with get_db() as db:
            duplicate_warnings = _duplicate_warnings(db, student_id, [prepared["embedding"]])
            _raise_if_duplicate_face(duplicate_warnings)
            face_id = student_face_repository.create_student_face(
                db,
                student_id,
                image_path,
                embedding_text,
                datetime.now().isoformat(timespec="seconds"),
            )
            face_count, deleted_image_paths = _trim_old_face_embeddings(db, student_id)
            write_audit_log(
                db,
                actor,
                "faces.upload",
                "student_face",
                face_id,
                f"{student['student_code']} - {student['full_name']}",
                {
                    "student_id": student_id,
                    "student_code": student["student_code"],
                    "face_count": face_count,
                    "trimmed_face_count": len(deleted_image_paths),
                    "duplicate_warnings": duplicate_warnings,
                },
                request,
            )
    except Exception:
        _delete_face_image_files([image_path])
        raise
    face_embedding_cache.invalidate()
    _delete_face_image_files(deleted_image_paths)
    return {
        "ok": True,
        "bbox": prepared["bbox"],
        "quality": prepared["quality"],
        "face_count": face_count,
        "max_faces": MAX_FACE_EMBEDDINGS_PER_STUDENT,
        "duplicate_warnings": duplicate_warnings,
        "message": "Đã thêm ảnh khuôn mặt bổ sung.",
    }


@router.post("/{student_id}/faces/scan")
async def replace_face_scan(student_id: int, request: Request, files: list[UploadFile] = File(...), actor=Depends(require_admin_or_lab_manager)):
    student = _get_student_or_404(student_id)
    if student["status"] != "active":
        raise HTTPException(status_code=400, detail="Không thể quét khuôn mặt cho sinh viên inactive.")
    if len(files) != FACE_SCAN_REQUIRED_FILES:
        raise HTTPException(status_code=400, detail=f"Vui lòng gửi đủ {FACE_SCAN_REQUIRED_FILES} ảnh quét.")

    validated = []
    for index, file in enumerate(files, start=1):
        data = await _read_limited_image_upload(file, f"Ảnh {index}")
        prepared = _prepare_face_upload(data, f"Ảnh {index}")
        validated.append({
            "data": prepared["data"],
            "embedding": prepared["embedding"],
            "bbox": prepared["bbox"],
            "quality": prepared["quality"],
        })

    created_at = datetime.now().isoformat(timespec="seconds")
    saved = []
    for item in validated:
        saved.append({
            "image_path": _save_face_image(student, item["data"]),
            "embedding": face_service.serialize_embedding(item["embedding"]),
            "bbox": item["bbox"],
        })

    try:
        with get_db() as db:
            duplicate_warnings = _duplicate_warnings(db, student_id, [item["embedding"] for item in validated])
            _raise_if_duplicate_face(duplicate_warnings)
            old_image_paths = student_face_repository.list_student_face_image_paths(db, student_id)
            student_face_repository.delete_student_faces(db, student_id)
            for item in saved:
                student_face_repository.create_student_face(
                    db,
                    student_id,
                    item["image_path"],
                    item["embedding"],
                    created_at,
                )
            write_audit_log(
                db,
                actor,
                "faces.scan_replace",
                "student",
                student_id,
                f"{student['student_code']} - {student['full_name']}",
                {
                    "student_id": student_id,
                    "student_code": student["student_code"],
                    "new_face_count": len(saved),
                    "deleted_face_count": len(old_image_paths),
                    "duplicate_warnings": duplicate_warnings,
                },
                request,
            )
    except Exception:
        _delete_face_image_files([item["image_path"] for item in saved])
        raise
    face_embedding_cache.invalidate()
    _delete_face_image_files(old_image_paths)

    return {
        "ok": True,
        "face_count": len(saved),
        "max_faces": MAX_FACE_EMBEDDINGS_PER_STUDENT,
        "bboxes": [item["bbox"] for item in saved],
        "qualities": [item["quality"] for item in validated],
        "duplicate_warnings": duplicate_warnings,
        "message": "Đã cập nhật bộ khuôn mặt mới.",
    }


@router.delete("/{student_id}/faces/{face_id}")
def delete_face(student_id: int, face_id: int, request: Request, actor=Depends(require_admin_or_lab_manager)):
    with get_db() as db:
        student = student_repository.get_student_identity(db, student_id)
        row = student_face_repository.get_student_face(db, student_id, face_id)
        student_face_repository.delete_student_face(db, student_id, face_id)
        if row:
            write_audit_log(
                db,
                actor,
                "faces.delete",
                "student_face",
                face_id,
                f"{student['student_code']} - {student['full_name']}" if student else None,
                {"student_id": student_id},
                request,
            )
    if row and row["image_path"]:
        face_embedding_cache.invalidate()
        _delete_face_image_files([row["image_path"]])
    elif row:
        face_embedding_cache.invalidate()
    return {"ok": True}

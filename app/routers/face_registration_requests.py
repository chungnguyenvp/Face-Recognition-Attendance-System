from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app.ai.embedding_cache import face_embedding_cache
from app.ai.face_engine import face_service
from app.db import get_db, row_to_dict
from app.repositories import face_registration_request_repository, student_face_repository, student_repository
from app.routers.deps import require_admin_or_lab_manager, require_student
from app.schemas.face_registration_requests import FaceRegistrationRequestReject
from app.schemas.students import FaceAnalyzeRequest
from app.services import face_registration_request_service
from app.services.student_face_service import (
    FACE_SCAN_REQUIRED_FILES,
    delete_face_image_files,
    prepare_face_upload,
    read_limited_image_upload,
)


student_router = APIRouter(
    prefix="/api/student/face-registration",
    tags=["student face registration"],
    dependencies=[Depends(require_student)],
)
staff_router = APIRouter(prefix="/api/face-registration-requests", tags=["face registration requests"])


def _service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(404, str(exc))
    if isinstance(exc, PermissionError):
        return HTTPException(403, str(exc))
    return HTTPException(409, str(exc))


def _public_item(row) -> dict | None:
    item = row_to_dict(row)
    if not item:
        return None
    for position in face_registration_request_service.FACE_REQUEST_POSITIONS:
        item.pop(f"{position}_image_path", None)
    item.pop("storage_key", None)
    return item


def _face_request_file(path):
    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


def _with_capacity_preview(item: dict | None, official_face_count: int) -> dict | None:
    if not item:
        return None
    capacity = face_registration_request_service.face_update_plan(official_face_count)
    item["official_face_count_now"] = official_face_count
    item["replace_count_now"] = capacity.removed_face_count
    item["face_count_after_approval"] = capacity.face_count_after
    return item


@student_router.get("")
def my_face_registration(user=Depends(require_student)):
    with get_db() as db:
        latest = face_registration_request_repository.get_latest_request_by_student(db, user["student_id"])
        face_count = student_face_repository.count_student_faces(db, user["student_id"])
    return {
        "official_face_count": face_count,
        "latest_request": _with_capacity_preview(_public_item(latest), face_count),
    }


@student_router.post("/analyze")
def analyze_my_face_registration(payload: FaceAnalyzeRequest, user=Depends(require_student)):
    try:
        image = face_service.read_image_from_base64(payload.image)
        return face_service.analyze_single_face_pose(image)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@student_router.post("/request")
async def submit_my_face_registration(
    request: Request,
    files: list[UploadFile] = File(...),
    note: str | None = Form(default=None, max_length=500),
    user=Depends(require_student),
):
    if len(files) != FACE_SCAN_REQUIRED_FILES:
        raise HTTPException(400, f"Vui long chup du {FACE_SCAN_REQUIRED_FILES} anh khuon mat.")
    prepared_images = []
    for index, file in enumerate(files, start=1):
        data = await read_limited_image_upload(file, f"Anh {index}")
        prepared_images.append(prepare_face_upload(data, f"Anh {index}"))
    normalized_note = (note or "").strip() or None
    try:
        with get_db() as db:
            student = student_repository.get_student_by_id(db, user["student_id"])
            if not student:
                raise LookupError("Khong tim thay ho so sinh vien.")
            item = face_registration_request_service.submit_request(
                db, student, user, prepared_images, normalized_note, request
            )
    except (ValueError, LookupError, PermissionError) as exc:
        raise _service_error(exc)
    return {"ok": True, "item": _public_item(item)}


@student_router.patch("/{request_id}/cancel")
def cancel_my_face_registration(request_id: int, request: Request, user=Depends(require_student)):
    try:
        with get_db() as db:
            student = student_repository.get_student_by_id(db, user["student_id"])
            if not student:
                raise LookupError("Khong tim thay ho so sinh vien.")
            item = face_registration_request_service.cancel_request(db, request_id, student, user, request)
    except (ValueError, LookupError, PermissionError) as exc:
        raise _service_error(exc)
    face_registration_request_service.delete_request_images(
        face_registration_request_service.request_image_paths(item)
    )
    return {"ok": True, "item": _public_item(item)}


@student_router.get("/{request_id}/images/{position}")
def my_face_registration_image(request_id: int, position: str, user=Depends(require_student)):
    with get_db() as db:
        item = face_registration_request_repository.get_request_by_id(db, request_id)
    if not item or item["student_id"] != user["student_id"]:
        raise HTTPException(404, "Khong tim thay yeu cau FaceID.")
    path = face_registration_request_service.request_image_path(item, position)
    if not path:
        raise HTTPException(404, "Khong tim thay anh yeu cau.")
    return _face_request_file(path)


@staff_router.get("")
def list_face_registration_requests(
    limit: int = 200,
    status: str | None = None,
    q: str | None = None,
    user=Depends(require_admin_or_lab_manager),
):
    with get_db() as db:
        rows = face_registration_request_repository.list_requests_for_staff(db, limit, status, q)
    return {"items": [_public_item(row) for row in rows], "count": len(rows)}


@staff_router.get("/{request_id}")
def get_face_registration_request(request_id: int, user=Depends(require_admin_or_lab_manager)):
    with get_db() as db:
        item = face_registration_request_repository.get_request_by_id(db, request_id)
        face_count = student_face_repository.count_student_faces(db, item["student_id"]) if item else 0
    if not item:
        raise HTTPException(404, "Khong tim thay yeu cau FaceID.")
    return {"item": _with_capacity_preview(_public_item(item), face_count)}


@staff_router.get("/{request_id}/images/{position}")
def face_registration_request_image(
    request_id: int, position: str, user=Depends(require_admin_or_lab_manager)
):
    with get_db() as db:
        item = face_registration_request_repository.get_request_by_id(db, request_id)
    if not item:
        raise HTTPException(404, "Khong tim thay yeu cau FaceID.")
    path = face_registration_request_service.request_image_path(item, position)
    if not path:
        raise HTTPException(404, "Khong tim thay anh yeu cau.")
    return _face_request_file(path)


@staff_router.patch("/{request_id}/approve")
def approve_face_registration_request(
    request_id: int, request: Request, user=Depends(require_admin_or_lab_manager)
):
    try:
        with get_db() as db:
            approval = face_registration_request_service.approve_request(db, request_id, user, request)
    except (ValueError, LookupError, PermissionError) as exc:
        raise _service_error(exc)
    face_embedding_cache.invalidate()
    delete_face_image_files(approval.replaced_image_paths)
    face_registration_request_service.delete_request_images(
        face_registration_request_service.request_image_paths(approval.item)
    )
    item = _public_item(approval.item)
    item["approval_summary"] = {
        "face_count_before": approval.face_count_before,
        "removed_face_count": approval.removed_face_count,
        "face_count_after": approval.face_count_after,
    }
    return {"ok": True, "item": item}


@staff_router.patch("/{request_id}/reject")
def reject_face_registration_request(
    request_id: int,
    payload: FaceRegistrationRequestReject,
    request: Request,
    user=Depends(require_admin_or_lab_manager),
):
    try:
        with get_db() as db:
            item = face_registration_request_service.reject_request(db, request_id, user, payload.reason, request)
    except (ValueError, LookupError, PermissionError) as exc:
        raise _service_error(exc)
    face_registration_request_service.delete_request_images(
        face_registration_request_service.request_image_paths(item)
    )
    return {"ok": True, "item": _public_item(item)}

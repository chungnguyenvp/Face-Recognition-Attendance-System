from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app.db import get_db, row_to_dict
from app.repositories import student_report_repository
from app.routers.deps import require_admin_or_lab_manager, require_student
from app.schemas.reports import ReportReview
from app.services import student_report_service
from app.services.private_storage import resolve_private_file


student_router = APIRouter(prefix="/api/student/reports", tags=["student reports"], dependencies=[Depends(require_student)])
staff_router = APIRouter(prefix="/api/reports", tags=["student reports"])


def _service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(404, str(exc))
    if isinstance(exc, PermissionError):
        return HTTPException(403, str(exc))
    return HTTPException(409, str(exc))


def _report_download(version) -> FileResponse:
    path = resolve_private_file(version["storage_path"], "report")
    if not path:
        raise HTTPException(404, "Khong tim thay file dinh kem.")
    return FileResponse(
        path,
        media_type=version["media_type"] or "application/octet-stream",
        filename=version["original_filename"] or path.name,
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "X-Content-Type-Options": "nosniff"},
    )


@student_router.get("/reviewers")
def list_report_reviewers(user=Depends(require_student)):
    with get_db() as db:
        rows = student_report_repository.list_active_lab_managers(db)
    return {"items": [row_to_dict(row) for row in rows], "count": len(rows)}


@student_router.get("")
def list_my_reports(limit: int = 100, user=Depends(require_student)):
    with get_db() as db:
        rows = student_report_repository.list_reports_for_student(db, user["student_id"], max(1, min(limit, 300)))
    return {"items": [row_to_dict(row) for row in rows], "count": len(rows)}


@student_router.post("")
async def submit_report(
    request: Request,
    title: str = Form(...),
    report_type: str = Form(...),
    description: str | None = Form(default=None),
    external_link: str | None = Form(default=None),
    reviewer_id: int | None = Form(default=None),
    attachment: UploadFile | None = File(default=None),
    user=Depends(require_student),
):
    try:
        with get_db() as db:
            item = await student_report_service.create_report(
                db, user, title, report_type, description, external_link, reviewer_id, attachment, request
            )
    except (ValueError, LookupError, PermissionError) as exc:
        raise _service_error(exc)
    return {"ok": True, "item": item}


@student_router.get("/{report_id}")
def get_my_report(report_id: int, user=Depends(require_student)):
    try:
        with get_db() as db:
            item = student_report_service.get_student_report_detail(db, user, report_id)
    except (LookupError, PermissionError) as exc:
        raise _service_error(exc)
    return {"item": item}


@student_router.post("/{report_id}/resubmit")
async def resubmit_report(
    report_id: int,
    request: Request,
    description: str | None = Form(default=None),
    external_link: str | None = Form(default=None),
    attachment: UploadFile | None = File(default=None),
    user=Depends(require_student),
):
    try:
        with get_db() as db:
            item = await student_report_service.resubmit_report(db, user, report_id, description, external_link, attachment, request)
    except (ValueError, LookupError, PermissionError) as exc:
        raise _service_error(exc)
    return {"ok": True, "item": item}


@student_router.get("/{report_id}/versions/{version_no}/download")
def download_my_report_file(report_id: int, version_no: int, user=Depends(require_student)):
    try:
        with get_db() as db:
            _, version = student_report_service.get_version_for_student(db, user, report_id, version_no)
    except (LookupError, PermissionError) as exc:
        raise _service_error(exc)
    return _report_download(version)


@staff_router.get("", dependencies=[Depends(require_admin_or_lab_manager)])
def list_staff_reports(limit: int = 200, status: str | None = None, report_type: str | None = None, q: str | None = None,
                       user=Depends(require_admin_or_lab_manager)):
    if status and status not in {"submitted", "revision_requested", "approved"}:
        raise HTTPException(422, "Trang thai khong hop le.")
    if report_type and report_type not in student_report_service.REPORT_TYPES:
        raise HTTPException(422, "Loai bao cao khong hop le.")
    with get_db() as db:
        reviewer_id = None if user.get("role") == "admin" else user["id"]
        rows = student_report_repository.list_reports_for_staff(db, reviewer_id, max(1, min(limit, 500)), status, report_type, q)
    return {"items": [row_to_dict(row) for row in rows], "count": len(rows)}


@staff_router.get("/{report_id}", dependencies=[Depends(require_admin_or_lab_manager)])
def get_staff_report(report_id: int, user=Depends(require_admin_or_lab_manager)):
    try:
        with get_db() as db:
            item = student_report_service.get_staff_report_detail(db, user, report_id)
    except (LookupError, PermissionError) as exc:
        raise _service_error(exc)
    return {"item": item}


@staff_router.post("/{report_id}/review")
def review_staff_report(report_id: int, payload: ReportReview, request: Request, user=Depends(require_admin_or_lab_manager)):
    try:
        with get_db() as db:
            item = student_report_service.review_report(db, user, report_id, payload, request)
    except (ValueError, LookupError, PermissionError) as exc:
        raise _service_error(exc)
    return {"ok": True, "item": item}


@staff_router.get("/{report_id}/versions/{version_no}/download", dependencies=[Depends(require_admin_or_lab_manager)])
def download_staff_report_file(report_id: int, version_no: int, user=Depends(require_admin_or_lab_manager)):
    try:
        with get_db() as db:
            _, version = student_report_service.get_version_for_staff(db, user, report_id, version_no)
    except (LookupError, PermissionError) as exc:
        raise _service_error(exc)
    return _report_download(version)

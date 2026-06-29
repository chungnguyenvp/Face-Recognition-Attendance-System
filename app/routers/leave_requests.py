from fastapi import APIRouter, Depends, HTTPException, Request

from app.db import get_db, row_to_dict
from app.repositories import leave_repository
from app.routers.deps import require_admin, require_admin_or_lab_manager, require_student
from app.schemas.leave import LeaveRequestApprove, LeaveRequestCreate, LeaveRequestReject, LeaveRequestRevoke
from app.services import leave_service


student_router = APIRouter(prefix="/api/student/leave-requests", tags=["leave requests"], dependencies=[Depends(require_student)])
staff_router = APIRouter(prefix="/api/leave-requests", tags=["leave requests"])


def _service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(404, str(exc))
    if isinstance(exc, PermissionError):
        return HTTPException(403, str(exc))
    return HTTPException(409, str(exc))


@student_router.get("")
def list_my_leave_requests(limit: int = 100, user=Depends(require_student)):
    with get_db() as db:
        rows = leave_repository.list_leave_requests_by_student(db, user["student_id"], limit)
    return {"items": [row_to_dict(row) for row in rows], "count": len(rows)}


@student_router.post("")
def create_my_leave_request(payload: LeaveRequestCreate, request: Request, user=Depends(require_student)):
    try:
        with get_db() as db:
            item = leave_service.create_leave_request(db, user, payload, request)
    except (ValueError, LookupError, PermissionError) as exc:
        raise _service_error(exc)
    return {"ok": True, "item": item}


@student_router.get("/{leave_id}")
def get_my_leave_request(leave_id: int, user=Depends(require_student)):
    with get_db() as db:
        row = leave_repository.get_leave_request_by_id(db, leave_id)
    if not row:
        raise HTTPException(404, "Khong tim thay don nghi.")
    if row["student_id"] != user["student_id"]:
        raise HTTPException(403, "Ban khong co quyen xem don nay.")
    return {"item": row_to_dict(row)}


@student_router.patch("/{leave_id}/cancel")
def cancel_my_leave_request(leave_id: int, request: Request, user=Depends(require_student)):
    try:
        with get_db() as db:
            item = leave_service.cancel_leave_request(db, user, leave_id, request)
    except (ValueError, LookupError, PermissionError) as exc:
        raise _service_error(exc)
    return {"ok": True, "item": item}


@staff_router.get("", dependencies=[Depends(require_admin_or_lab_manager)])
def list_leave_requests(limit: int = 200, status: str | None = None, leave_type: str | None = None,
                        date_from: str | None = None, date_to: str | None = None, q: str | None = None):
    with get_db() as db:
        rows = leave_repository.list_leave_requests_for_staff(db, limit, status, leave_type, date_from, date_to, q)
    return {"items": [row_to_dict(row) for row in rows], "count": len(rows)}


@staff_router.get("/{leave_id}", dependencies=[Depends(require_admin_or_lab_manager)])
def get_leave_request(leave_id: int):
    with get_db() as db:
        row = leave_repository.get_leave_request_by_id(db, leave_id)
    if not row:
        raise HTTPException(404, "Khong tim thay don nghi.")
    return {"item": row_to_dict(row)}


@staff_router.patch("/{leave_id}/approve")
def approve_leave_request(leave_id: int, payload: LeaveRequestApprove, request: Request, user=Depends(require_admin_or_lab_manager)):
    try:
        with get_db() as db:
            item = leave_service.review_leave_request(db, user, leave_id, "approved", payload.reviewer_note, request)
    except (ValueError, LookupError, PermissionError) as exc:
        raise _service_error(exc)
    return {"ok": True, "item": item}


@staff_router.patch("/{leave_id}/reject")
def reject_leave_request(leave_id: int, payload: LeaveRequestReject, request: Request, user=Depends(require_admin_or_lab_manager)):
    try:
        with get_db() as db:
            item = leave_service.review_leave_request(db, user, leave_id, "rejected", payload.reviewer_note, request)
    except (ValueError, LookupError, PermissionError) as exc:
        raise _service_error(exc)
    return {"ok": True, "item": item}


@staff_router.patch("/{leave_id}/revoke")
def revoke_leave_request(leave_id: int, payload: LeaveRequestRevoke, request: Request, user=Depends(require_admin)):
    try:
        with get_db() as db:
            item = leave_service.revoke_leave_request(db, user, leave_id, payload.reviewer_note, request)
    except (ValueError, LookupError, PermissionError) as exc:
        raise _service_error(exc)
    return {"ok": True, "item": item}

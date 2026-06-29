from fastapi import APIRouter, Depends, HTTPException, Request

from app.db import get_db, row_to_dict
from app.repositories import access_log_repository
from app.routers.deps import require_admin, require_admin_or_lab_manager
from app.services.attendance_service import recalculate_student_attendance_record
from app.services.audit_service import write_audit_log

router = APIRouter(prefix="/api", tags=["access_logs"])


@router.get("/access-logs", dependencies=[Depends(require_admin_or_lab_manager)])
def access_logs(
    limit: int = 100,
    date_from: str | None = None,
    date_to: str | None = None,
    action: str | None = None,
    result: str | None = None,
    q: str | None = None,
):
    with get_db() as db:
        rows = access_log_repository.list_access_logs(db, limit, date_from, date_to, action, result, q)
    return {"items": [row_to_dict(r) for r in rows], "count": len(rows)}


@router.delete("/access-logs/{log_id}")
def delete_access_log(log_id: int, request: Request, actor=Depends(require_admin)):
    should_recalculate = False
    student_id = None
    attendance_date = None
    with get_db() as db:
        current = access_log_repository.get_access_log_delete_summary(db, log_id)
        if not current:
            raise HTTPException(status_code=404, detail="Không tìm thấy lịch sử.")
        student_id = current["student_id"]
        attendance_date = current["attendance_date"]
        should_recalculate = (
            student_id is not None
            and attendance_date is not None
            and current["result"] == "success"
            and current["action"] in {"check_in", "check_out"}
        )
        access_log_repository.delete_access_log(db, log_id)
        write_audit_log(
            db,
            actor,
            "access_logs.delete",
            "access_log",
            log_id,
            f"{current['student_code'] or 'Unknown'} {current['action']} {current['attendance_date'] or ''}".strip(),
            {
                "student_id": current["student_id"],
                "student_code": current["student_code"],
                "full_name": current["full_name"],
                "action": current["action"],
                "result": current["result"],
                "attendance_date": current["attendance_date"],
            },
            request,
        )
    recalculated = (
        recalculate_student_attendance_record(student_id, attendance_date)
        if should_recalculate
        else False
    )
    return {"ok": True, "attendance_recalculated": recalculated}

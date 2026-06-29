from fastapi import APIRouter, Depends, HTTPException, Request

from app.db import get_db, row_to_dict
from app.repositories import alert_repository
from app.routers.deps import require_admin, require_admin_or_lab_manager
from app.schemas.alerts import AlertStatusUpdate
from app.services.attendance_service import mark_missing_checkouts
from app.services.audit_service import write_audit_log

router = APIRouter(prefix="/api", tags=["alerts"])


@router.get("/alerts", dependencies=[Depends(require_admin_or_lab_manager)])
def alerts(
    limit: int = 100,
    date_from: str | None = None,
    date_to: str | None = None,
    type: str | None = None,
    status: str | None = None,
    q: str | None = None,
):
    with get_db() as db:
        rows = alert_repository.list_alerts(db, limit, date_from, date_to, type, status, q)
    return {"items": [row_to_dict(r) for r in rows], "count": len(rows)}


@router.post("/alerts/scan-missing-checkouts")
def scan_missing_checkouts(request: Request, actor=Depends(require_admin_or_lab_manager)):
    created = mark_missing_checkouts()
    with get_db() as db:
        write_audit_log(
            db,
            actor,
            "alerts.scan_missing_checkouts",
            "alert",
            details={"created": created},
            request=request,
        )
    return {"ok": True, "created": created}


@router.put("/alerts/{alert_id}/status")
def update_alert_status(alert_id: int, payload: AlertStatusUpdate, request: Request, actor=Depends(require_admin_or_lab_manager)):
    if payload.status not in {"new", "resolved", "ignored"}:
        raise HTTPException(status_code=400, detail="Trạng thái cảnh báo không hợp lệ.")
    with get_db() as db:
        current = alert_repository.get_alert_summary(db, alert_id)
        if not current:
            raise HTTPException(status_code=404, detail="Không tìm thấy cảnh báo.")
        alert_repository.update_alert_status(db, alert_id, payload.status)
        row = alert_repository.get_alert_by_id(db, alert_id)
        if current["status"] != payload.status:
            write_audit_log(
                db,
                actor,
                "alerts.status.update",
                "alert",
                alert_id,
                current["message"],
                {
                    "type": current["type"],
                    "changes": {"status": {"old": current["status"], "new": payload.status}},
                },
                request,
            )
    return {"item": row_to_dict(row)}


@router.delete("/alerts/{alert_id}")
def delete_alert(alert_id: int, request: Request, actor=Depends(require_admin)):
    with get_db() as db:
        current = alert_repository.get_alert_summary(db, alert_id)
        if not current:
            raise HTTPException(status_code=404, detail="Không tìm thấy cảnh báo.")
        alert_repository.delete_alert(db, alert_id)
        write_audit_log(
            db,
            actor,
            "alerts.delete",
            "alert",
            alert_id,
            current["message"],
            {"type": current["type"], "status": current["status"]},
            request,
        )
    return {"ok": True}

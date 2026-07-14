from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.db import get_db
from app.repositories import attendance_export_repository
from app.routers.deps import require_admin_or_lab_manager
from app.schemas.exports import AttendanceExportRequest
from app.services.attendance_export_service import ExportRowLimitError, build_attendance_workbook
from app.services.audit_service import write_audit_log


router = APIRouter(prefix="/api/exports", tags=["exports"])


@router.post("/attendance")
def export_attendance(
    payload: AttendanceExportRequest,
    request: Request,
    actor=Depends(require_admin_or_lab_manager),
):
    filters = {
        "date_from": payload.date_from.isoformat(),
        "date_to": payload.date_to.isoformat(),
        "status": payload.status,
        "q": payload.q,
        "include_summary": payload.include_summary,
        "include_details": payload.include_details,
    }
    with get_db() as db:
        rows = attendance_export_repository.list_attendance_export_rows(
            db,
            filters["date_from"],
            filters["date_to"],
            payload.status,
            payload.q,
        )
        try:
            workbook, row_count, filename = build_attendance_workbook(rows, payload, actor)
        except ExportRowLimitError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        write_audit_log(
            db,
            actor,
            "attendance.export_xlsx",
            "attendance_export",
            entity_label=f"{filters['date_from']} - {filters['date_to']}",
            details={**filters, "row_count": row_count},
            request=request,
        )

    return Response(
        content=workbook,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )

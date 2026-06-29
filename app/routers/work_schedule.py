from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from app.db import get_db, row_to_dict
from app.repositories import work_schedule_repository
from app.routers.deps import require_admin, require_admin_or_lab_manager
from app.schemas.work_schedule import CalendarExceptionCreate, CalendarExceptionUpdate, WorkScheduleUpdate
from app.services import work_schedule_service
from app.services.attendance_record_service import recalculate_attendance_date
from app.services.audit_service import audit_diff, write_audit_log


router = APIRouter(prefix="/api/work-schedule", tags=["work_schedule"])


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _schedule_item(db, value: date | None = None) -> dict:
    return work_schedule_service.schedule_payload(db, value)


@router.get("/today", dependencies=[Depends(require_admin_or_lab_manager)])
def today_schedule():
    with get_db() as db:
        return work_schedule_service.get_day_policy(db)


@router.get("/settings", dependencies=[Depends(require_admin_or_lab_manager)])
def get_settings(effective_date: date | None = None):
    with get_db() as db:
        return _schedule_item(db, effective_date)


@router.put("/settings")
def update_settings(payload: WorkScheduleUpdate, request: Request, actor=Depends(require_admin)):
    effective_from = payload.effective_from or date.today()
    if effective_from < date.today():
        raise HTTPException(status_code=400, detail="Lịch tuần chỉ được áp dụng từ hôm nay trở đi.")
    now = _now()
    values = payload.model_dump()
    values["effective_from"] = effective_from.isoformat()
    values["updated_at"] = now
    with get_db() as db:
        before = _schedule_item(db, effective_from)
        work_schedule_repository.upsert_schedule(db, values)
        after = _schedule_item(db, effective_from)
        updated = recalculate_attendance_date(db, effective_from.isoformat()) if effective_from == date.today() else 0
        changes = audit_diff(before, after, [
            "monday_enabled", "tuesday_enabled", "wednesday_enabled", "thursday_enabled", "friday_enabled",
            "saturday_enabled", "sunday_enabled", "start_time", "end_time", "late_allowed_minutes",
            "early_leave_allowed_minutes", "checkout_cutoff_time",
        ])
        write_audit_log(
            db, actor, "work_schedule.settings.update", "work_schedule", values["effective_from"],
            f"Lịch làm việc từ {values['effective_from']}",
            {"effective_from": values["effective_from"], "changes": changes, "attendance_recalculated": updated}, request,
        )
    return {"ok": True, "settings": after, "attendance_recalculated": updated}


@router.get("/exceptions", dependencies=[Depends(require_admin_or_lab_manager)])
def list_exceptions(date_from: date | None = None, date_to: date | None = None):
    with get_db() as db:
        rows = work_schedule_repository.list_exceptions(
            db, date_from.isoformat() if date_from else None, date_to.isoformat() if date_to else None,
        )
        return {"items": [row_to_dict(row) for row in rows], "count": len(rows)}


def _exception_values(payload, now: str) -> dict:
    return {
        "exception_date": payload.exception_date.isoformat(), "exception_type": payload.exception_type,
        "holiday_name": payload.holiday_name, "note": payload.note, "created_at": now, "updated_at": now,
    }


@router.post("/exceptions")
def create_exception(payload: CalendarExceptionCreate, request: Request, actor=Depends(require_admin)):
    values = _exception_values(payload, _now())
    with get_db() as db:
        if work_schedule_repository.get_exception_for_date(db, values["exception_date"]):
            raise HTTPException(status_code=409, detail="Ngày này đã có cấu hình ngoại lệ.")
        exception_id = work_schedule_repository.upsert_exception(db, None, values)
        recalculated = recalculate_attendance_date(db, values["exception_date"])
        item = row_to_dict(work_schedule_repository.get_exception_by_id(db, exception_id))
        write_audit_log(db, actor, "work_schedule.exception.create", "work_schedule_exception", exception_id,
                        values["holiday_name"], {"exception": item, "attendance_recalculated": recalculated}, request)
    return {"ok": True, "item": item, "attendance_recalculated": recalculated}


@router.put("/exceptions/{exception_id}")
def update_exception(exception_id: int, payload: CalendarExceptionUpdate, request: Request, actor=Depends(require_admin)):
    values = _exception_values(payload, _now())
    with get_db() as db:
        previous = work_schedule_repository.get_exception_by_id(db, exception_id)
        if not previous:
            raise HTTPException(status_code=404, detail="Không tìm thấy ngày nghỉ đặc biệt.")
        duplicate = work_schedule_repository.get_exception_for_date(db, values["exception_date"])
        if duplicate and duplicate["id"] != exception_id:
            raise HTTPException(status_code=409, detail="Ngày này đã có cấu hình ngoại lệ.")
        work_schedule_repository.upsert_exception(db, exception_id, values)
        affected_dates = {previous["exception_date"], values["exception_date"]}
        recalculated = sum(recalculate_attendance_date(db, item) for item in affected_dates)
        item = row_to_dict(work_schedule_repository.get_exception_by_id(db, exception_id))
        write_audit_log(db, actor, "work_schedule.exception.update", "work_schedule_exception", exception_id,
                        values["holiday_name"], {"before": row_to_dict(previous), "after": item, "attendance_recalculated": recalculated}, request)
    return {"ok": True, "item": item, "attendance_recalculated": recalculated}


@router.delete("/exceptions/{exception_id}")
def delete_exception(exception_id: int, request: Request, actor=Depends(require_admin)):
    with get_db() as db:
        previous = work_schedule_repository.get_exception_by_id(db, exception_id)
        if not previous:
            raise HTTPException(status_code=404, detail="Không tìm thấy ngày nghỉ đặc biệt.")
        work_schedule_repository.delete_exception(db, exception_id)
        recalculated = recalculate_attendance_date(db, previous["exception_date"])
        write_audit_log(db, actor, "work_schedule.exception.delete", "work_schedule_exception", exception_id,
                        previous["holiday_name"], {"exception": row_to_dict(previous), "attendance_recalculated": recalculated}, request)
    return {"ok": True, "attendance_recalculated": recalculated}


@router.get("/calendar", dependencies=[Depends(require_admin_or_lab_manager)])
def calendar(year: int, month: int):
    if not 2000 <= year <= 2100 or not 1 <= month <= 12:
        raise HTTPException(status_code=400, detail="Tháng hoặc năm không hợp lệ.")
    with get_db() as db:
        return {"year": year, "month": month, "days": work_schedule_service.calendar_preview(db, year, month)}

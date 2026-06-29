from fastapi import APIRouter, Depends, Request
from app.db import get_db
from app.repositories import settings_repository
from app.routers.deps import require_admin, require_admin_or_lab_manager
from app.schemas.settings import SettingsUpdate
from app.services.audit_service import audit_diff, write_audit_log
from app.ai.liveness_engine import liveness_service

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", dependencies=[Depends(require_admin_or_lab_manager)])
def get_settings():
    with get_db() as db:
        return settings_repository.get_settings_map(db)


@router.get("/liveness-status", dependencies=[Depends(require_admin_or_lab_manager)])
def liveness_status():
    enabled = liveness_service.is_enabled()
    if not enabled:
        return {"enabled": False, "status": "disabled", "message": "Chống giả mạo đang tắt."}

    if liveness_service.ensure_loaded():
        return {"enabled": True, "status": "ready", "message": "Model chống giả mạo sẵn sàng."}

    return {"enabled": True, "status": "error", "message": "Model chống giả mạo chưa sẵn sàng."}


@router.put("")
def update_settings(payload: SettingsUpdate, request: Request, actor=Depends(require_admin)):
    values = {
        "face_threshold": str(payload.face_threshold),
        "check_cooldown_seconds": str(payload.check_cooldown_seconds),
        "frame_skip": str(payload.frame_skip),
    }
    optional_values = {
        "camera_mode": payload.camera_mode,
        "check_in_camera_device_id": payload.check_in_camera_device_id,
        "check_out_camera_device_id": payload.check_out_camera_device_id,
        "auto_start_cameras": "true" if payload.auto_start_cameras else "false" if payload.auto_start_cameras is not None else None,
        "check_in_camera_source": payload.check_in_camera_source,
        "check_out_camera_source": payload.check_out_camera_source,
        "liveness_enabled": "true" if payload.liveness_enabled else "false" if payload.liveness_enabled is not None else None,
        "missing_checkout_cutoff_time": payload.missing_checkout_cutoff_time,
        "work_start_time": payload.work_start_time,
        "work_end_time": payload.work_end_time,
        "late_grace_minutes": str(payload.late_grace_minutes) if payload.late_grace_minutes is not None else None,
        "early_leave_grace_minutes": str(payload.early_leave_grace_minutes) if payload.early_leave_grace_minutes is not None else None,
    }
    values.update({key: value for key, value in optional_values.items() if value is not None})

    with get_db() as db:
        before = settings_repository.get_settings_map(db)
        settings_repository.upsert_settings(db, values)
        after = {**before, **values}
        changes = audit_diff(before, after, list(values.keys()))
        if changes:
            write_audit_log(
                db,
                actor,
                "settings.update",
                "settings",
                details={"changes": changes},
                request=request,
            )
    return {"ok": True}

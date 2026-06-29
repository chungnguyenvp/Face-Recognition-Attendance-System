from fastapi import APIRouter, Depends, HTTPException

from app.routers.deps import require_admin, require_admin_or_lab_manager
from app.schemas.server_cameras import CameraStartPayload
from app.services.server_camera_service import server_camera_manager


router = APIRouter(prefix="/api/server-cameras", tags=["server-cameras"])


def _validate_action(action: str) -> str:
    if action not in {"check_in", "check_out"}:
        raise HTTPException(status_code=400, detail="Invalid camera action.")
    return action


@router.get("/status", dependencies=[Depends(require_admin_or_lab_manager)])
def camera_status():
    return server_camera_manager.status()


@router.post("/{action}/start")
def start_camera(action: str, payload: CameraStartPayload | None = None, _actor=Depends(require_admin)):
    return server_camera_manager.start(_validate_action(action), payload.source if payload else None)


@router.post("/{action}/stop")
def stop_camera(action: str, _actor=Depends(require_admin)):
    return server_camera_manager.stop(_validate_action(action))


@router.post("/start-all")
def start_all_cameras(_actor=Depends(require_admin)):
    return server_camera_manager.start_all_configured()


@router.post("/stop-all")
def stop_all_cameras(_actor=Depends(require_admin)):
    return server_camera_manager.stop_all()

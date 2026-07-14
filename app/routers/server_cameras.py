import time

from fastapi import APIRouter, Cookie, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.routers.deps import (
    STAFF_ROLES,
    require_admin,
    require_admin_or_lab_manager,
    user_from_session_token,
)
from app.schemas.server_cameras import CameraStartRequest
from app.services.server_camera_service import MJPEG_BOUNDARY, server_camera_manager


router = APIRouter(prefix="/api/server-cameras", tags=["server-cameras"])


def _validate_action(action: str) -> str:
    if action not in {"check_in", "check_out"}:
        raise HTTPException(status_code=400, detail="Invalid camera action.")
    return action


@router.get("/status", dependencies=[Depends(require_admin_or_lab_manager)])
def camera_status():
    return server_camera_manager.status()


def _authorized_camera_stream(action: str, session_token: str | None, actor: dict):
    last_auth_check = time.monotonic()
    for chunk in server_camera_manager.mjpeg_stream(action):
        now = time.monotonic()
        if now - last_auth_check >= 5.0:
            current = user_from_session_token(session_token)
            if (
                not current
                or current.get("id") != actor.get("id")
                or current.get("status") != "active"
                or current.get("role") not in STAFF_ROLES
            ):
                return
            last_auth_check = now
        yield chunk


@router.get("/{action}/stream")
def camera_stream(
    action: str,
    session_token: str | None = Cookie(default=None),
    actor=Depends(require_admin_or_lab_manager),
):
    active_action = _validate_action(action)
    if not server_camera_manager.status(active_action)["running"]:
        raise HTTPException(status_code=409, detail="Camera is not running.")
    return StreamingResponse(
        _authorized_camera_stream(active_action, session_token, actor),
        media_type=f"multipart/x-mixed-replace; boundary={MJPEG_BOUNDARY}",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{action}/start")
def start_camera(
    action: str,
    _payload: CameraStartRequest | None = None,
    _actor=Depends(require_admin),
):
    return server_camera_manager.start(_validate_action(action))


@router.post("/{action}/stop")
def stop_camera(action: str, _actor=Depends(require_admin)):
    return server_camera_manager.stop(_validate_action(action))


@router.post("/start-all")
def start_all_cameras(_actor=Depends(require_admin)):
    return server_camera_manager.start_all_configured()


@router.post("/stop-all")
def stop_all_cameras(_actor=Depends(require_admin)):
    return server_camera_manager.stop_all()

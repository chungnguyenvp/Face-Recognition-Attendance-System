import base64
import binascii
import json
import logging
from io import BytesIO
from urllib.parse import urlsplit

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.db import get_setting
from app.routers.deps import user_from_session_token
from app.ai.face_engine import face_service
from app.services.realtime_recognition_service import load_known_faces, process_realtime_frame
from app.services.realtime_session_service import cleanup_presence_sessions, session_decision


router = APIRouter(tags=["realtime"])
logger = logging.getLogger(__name__)

WS_POLICY_VIOLATION = 1008
WS_MESSAGE_TOO_BIG = 1009
SAFE_FRAME_ERROR_MESSAGE = "Khong xu ly duoc khung hinh."
ALLOWED_REALTIME_IMAGE_FORMATS = {"JPEG", "PNG"}


class RealtimePayloadError(ValueError):
    def __init__(self, code: str, message: str = SAFE_FRAME_ERROR_MESSAGE, close_code: int | None = None):
        super().__init__(message)
        self.code = code
        self.close_code = close_code
        self.client_message = message


def _configured_websocket_origins() -> set[str]:
    return {
        origin.strip().rstrip("/")
        for origin in settings.websocket_allowed_origins.split(",")
        if origin.strip()
    }


def is_allowed_websocket_origin(websocket: WebSocket) -> bool:
    origin = (websocket.headers.get("origin") or "").strip().rstrip("/")
    if not origin:
        return False
    if origin in _configured_websocket_origins():
        return True

    host = (websocket.headers.get("host") or "").strip().lower()
    parsed = urlsplit(origin)
    return parsed.scheme in {"http", "https"} and parsed.netloc.lower() == host


def _utf8_size(text: str) -> int:
    return len(text.encode("utf-8"))


def parse_realtime_payload(payload: str) -> str | None:
    if _utf8_size(payload) > settings.websocket_max_message_bytes:
        raise RealtimePayloadError("message_too_large", "Khung hinh qua lon.", WS_MESSAGE_TOO_BIG)

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RealtimePayloadError("invalid_payload") from exc

    if not isinstance(data, dict):
        raise RealtimePayloadError("invalid_payload")

    image_data = data.get("image")
    if image_data is None:
        return None
    if not isinstance(image_data, str):
        raise RealtimePayloadError("invalid_payload")
    return image_data


def decode_realtime_image(image_data: str):
    if "," in image_data:
        header, image_data = image_data.split(",", 1)
        header = header.lower()
        if header.startswith("data:") and not (header.startswith("data:image/jpeg") or header.startswith("data:image/png")):
            raise RealtimePayloadError("invalid_image")

    max_base64_len = ((settings.websocket_max_image_bytes + 2) // 3) * 4 + 4
    if len(image_data) > max_base64_len:
        raise RealtimePayloadError("image_too_large", "Khung hinh qua lon.", WS_MESSAGE_TOO_BIG)

    try:
        image_bytes = base64.b64decode(image_data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise RealtimePayloadError("invalid_image") from exc

    if not image_bytes:
        raise RealtimePayloadError("invalid_image")
    if len(image_bytes) > settings.websocket_max_image_bytes:
        raise RealtimePayloadError("image_too_large", "Khung hinh qua lon.", WS_MESSAGE_TOO_BIG)

    try:
        with Image.open(BytesIO(image_bytes)) as probe:
            if probe.format not in ALLOWED_REALTIME_IMAGE_FORMATS:
                raise RealtimePayloadError("invalid_image")
            width, height = probe.size
    except RealtimePayloadError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise RealtimePayloadError("invalid_image") from exc

    if width <= 0 or height <= 0 or width * height > settings.websocket_max_image_pixels:
        raise RealtimePayloadError("image_too_large", "Khung hinh qua lon.", WS_MESSAGE_TOO_BIG)

    return face_service.read_image_from_bytes(image_bytes)


async def websocket_auth(websocket: WebSocket) -> bool:
    token = websocket.cookies.get("session_token")
    user = user_from_session_token(token)
    return bool(user and user["role"] in {"admin", "lab_manager"} and user["status"] == "active")


@router.websocket("/ws/recognize")
async def recognize_ws(websocket: WebSocket):
    if not is_allowed_websocket_origin(websocket):
        await websocket.close(code=WS_POLICY_VIOLATION)
        return

    await websocket.accept()
    if not await websocket_auth(websocket):
        await websocket.send_json({"type": "error", "message": "Chua dang nhap hoac phien het han."})
        await websocket.close()
        return

    frame_count = 0
    try:
        while True:
            payload = await websocket.receive_text()
            if not await websocket_auth(websocket):
                await websocket.send_json({"type": "error", "message": "Phien dang nhap da het han hoac bi thu hoi."})
                await websocket.close()
                return

            frame_count += 1
            try:
                image_data = parse_realtime_payload(payload)
            except RealtimePayloadError as exc:
                await websocket.send_json({"type": "error", "code": exc.code, "message": exc.client_message})
                if exc.close_code:
                    await websocket.close(code=exc.close_code)
                    return
                continue

            if not image_data:
                continue

            frame_skip = int(get_setting("frame_skip", 5))
            if frame_skip > 1 and frame_count % frame_skip != 0:
                await websocket.send_json({"type": "skip"})
                continue

            requested_action = websocket.query_params.get("action")
            action = requested_action if requested_action in {"check_in", "check_out"} else get_setting("camera_mode", "check_in")

            try:
                image = decode_realtime_image(image_data)
            except RealtimePayloadError as exc:
                await websocket.send_json({"type": "error", "code": exc.code, "message": exc.client_message})
                if exc.close_code:
                    await websocket.close(code=exc.close_code)
                    return
                continue

            result = process_realtime_frame(
                image,
                action,
                image_data,
                setting_getter=get_setting,
                known_faces_loader=load_known_faces,
                recognize_faces=face_service.recognize_faces,
                cleanup_sessions=cleanup_presence_sessions,
                decide_session=session_decision,
            )
            await websocket.send_json(result)
    except WebSocketDisconnect:
        return
    except Exception:
        logger.exception("Unexpected realtime websocket error")
        await websocket.send_json({"type": "error", "code": "internal_error", "message": SAFE_FRAME_ERROR_MESSAGE})

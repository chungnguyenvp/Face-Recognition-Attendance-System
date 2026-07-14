import base64
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import cv2

from app.core.config import settings
from app.services.realtime_recognition_service import process_realtime_frame
from app.services.realtime_session_service import clear_presence_scope


VALID_ACTIONS = {"check_in", "check_out"}
MJPEG_BOUNDARY = "frame"


def parse_camera_source(value: str | int | None):
    if value is None:
        return None
    if isinstance(value, int):
        return value
    clean = str(value).strip()
    if not clean:
        return None
    if clean.isdigit():
        return int(clean)
    return clean


def encode_frame_jpeg(frame, quality: int = 85) -> bytes | None:
    safe_quality = max(30, min(95, int(quality)))
    ok, buffer = cv2.imencode(
        ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), safe_quality]
    )
    if not ok:
        return None
    return buffer.tobytes()


def encode_frame_data_url(frame) -> str | None:
    jpeg = encode_frame_jpeg(frame, 85)
    if jpeg is None:
        return None
    encoded = base64.b64encode(jpeg).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def display_camera_source(source: str) -> str:
    clean = str(source or "")
    if "://" not in clean:
        return clean
    try:
        parsed = urlsplit(clean)
        host = parsed.hostname or ""
        if parsed.port:
            host = f"{host}:{parsed.port}"
        if not parsed.username and not parsed.password:
            return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
        return urlunsplit(
            (parsed.scheme, f"***@{host}", parsed.path, "", "")
        )
    except ValueError:
        return "configured-camera-source"


@dataclass
class CameraRuntime:
    action: str
    source: str = ""
    running: bool = False
    connected: bool = False
    last_error: str | None = None
    last_started_at: str | None = None
    last_frame_at: str | None = None
    last_result_at: str | None = None
    last_result: dict | None = None
    frames_read: int = 0
    frames_processed: int = 0
    latest_jpeg: bytes | None = field(default=None, repr=False)
    frame_width: int = 0
    frame_height: int = 0
    frame_sequence: int = 0
    last_result_sequence: int = 0
    session_scope: str | None = field(default=None, repr=False)
    thread: threading.Thread | None = field(default=None, repr=False)
    stop_event: threading.Event = field(default_factory=threading.Event, repr=False)


class ServerCameraManager:
    def __init__(self):
        self._cameras = {action: CameraRuntime(action=action) for action in VALID_ACTIONS}
        self._lock = threading.RLock()
        self._frame_condition = threading.Condition(self._lock)

    def configured_source(self, action: str) -> str:
        source = (
            settings.check_out_camera_source
            if action == "check_out"
            else settings.check_in_camera_source
        )
        return str(source or "").strip()

    def auto_start_enabled(self) -> bool:
        return settings.auto_start_cameras

    def start_all_configured(self) -> dict:
        statuses = {}
        for action in ("check_in", "check_out"):
            source = self.configured_source(action)
            if source:
                statuses[action] = self.start(action)
            else:
                statuses[action] = self.status(action)
        return statuses

    def stop_all(self) -> dict:
        return {action: self.stop(action) for action in ("check_in", "check_out")}

    def start(self, action: str) -> dict:
        self._validate_action(action)
        source = self.configured_source(action)
        parsed_source = parse_camera_source(source)
        if parsed_source is None:
            with self._lock:
                runtime = self._cameras[action]
                runtime.last_error = "Camera source is empty."
            return self.status(action)

        with self._lock:
            runtime = self._cameras[action]
            if runtime.running:
                runtime.source = str(source)
                return self._status_unlocked(runtime)
            runtime.source = str(source)
            runtime.running = True
            runtime.connected = False
            runtime.last_error = None
            runtime.last_started_at = datetime.now().isoformat(timespec="seconds")
            runtime.last_frame_at = None
            runtime.last_result_at = None
            runtime.last_result = None
            runtime.frames_read = 0
            runtime.frames_processed = 0
            runtime.latest_jpeg = None
            runtime.frame_width = 0
            runtime.frame_height = 0
            runtime.frame_sequence = 0
            runtime.last_result_sequence = 0
            runtime.session_scope = f"server-camera:{action}:{uuid4().hex}"
            runtime.stop_event.clear()
            runtime.thread = threading.Thread(
                target=self._run_camera,
                args=(action, parsed_source, runtime.session_scope),
                name=f"server-camera-{action}",
                daemon=True,
            )
            runtime.thread.start()
            return self._status_unlocked(runtime)

    def stop(self, action: str) -> dict:
        self._validate_action(action)
        with self._lock:
            runtime = self._cameras[action]
            thread = runtime.thread
            runtime.stop_event.set()
        if thread and thread.is_alive():
            thread.join(timeout=3)
        with self._lock:
            runtime = self._cameras[action]
            if thread and thread.is_alive():
                runtime.connected = False
                runtime.last_error = "Camera worker is still stopping."
                return self._status_unlocked(runtime)
            session_scope = runtime.session_scope
            runtime.running = False
            runtime.connected = False
            runtime.latest_jpeg = None
            runtime.frame_width = 0
            runtime.frame_height = 0
            runtime.session_scope = None
            runtime.thread = None
            status = self._status_unlocked(runtime)
            self._frame_condition.notify_all()
        if session_scope:
            clear_presence_scope(session_scope)
        return status

    def status(self, action: str | None = None):
        with self._lock:
            if action:
                self._validate_action(action)
                return self._status_unlocked(self._cameras[action])
            return {key: self._status_unlocked(runtime) for key, runtime in self._cameras.items()}

    def mjpeg_stream(self, action: str):
        self._validate_action(action)
        last_sequence = -1
        while True:
            with self._frame_condition:
                runtime = self._cameras[action]
                self._frame_condition.wait_for(
                    lambda: (
                        runtime.frame_sequence != last_sequence
                        and runtime.latest_jpeg is not None
                    )
                    or not runtime.running,
                    timeout=1.0,
                )
                runtime = self._cameras[action]
                if runtime.latest_jpeg is None:
                    if not runtime.running:
                        return
                    continue
                if runtime.frame_sequence == last_sequence:
                    if not runtime.running:
                        return
                    continue
                jpeg = runtime.latest_jpeg
                sequence = runtime.frame_sequence
            last_sequence = sequence
            yield (
                f"--{MJPEG_BOUNDARY}\r\n"
                "Content-Type: image/jpeg\r\n"
                f"Content-Length: {len(jpeg)}\r\n"
                f"X-Frame-Sequence: {sequence}\r\n\r\n"
            ).encode("ascii") + jpeg + b"\r\n"

    def _publish_preview(self, action: str, frame, jpeg: bytes) -> int:
        height, width = frame.shape[:2]
        with self._frame_condition:
            runtime = self._cameras[action]
            runtime.latest_jpeg = jpeg
            runtime.frame_width = int(width)
            runtime.frame_height = int(height)
            runtime.frame_sequence += 1
            sequence = runtime.frame_sequence
            self._frame_condition.notify_all()
            return sequence

    def _run_camera(self, action: str, source, session_scope: str) -> None:
        reconnect_seconds = max(1.0, float(settings.camera_reconnect_seconds))
        process_interval = max(0.05, float(settings.server_camera_process_interval_seconds))
        preview_fps = max(1.0, float(settings.server_camera_preview_fps))
        preview_interval = 1.0 / preview_fps
        preview_quality = max(30, min(95, int(settings.server_camera_jpeg_quality)))
        cap = None
        try:
            while not self._cameras[action].stop_event.is_set():
                cap = cv2.VideoCapture(source)
                if not cap.isOpened():
                    self._set_error(action, "Cannot open camera source.")
                    self._sleep_or_stop(action, reconnect_seconds)
                    cap.release()
                    cap = None
                    continue

                with self._lock:
                    runtime = self._cameras[action]
                    runtime.connected = True
                    runtime.last_error = None

                last_processed = 0.0
                last_preview = 0.0
                while not self._cameras[action].stop_event.is_set():
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        self._set_error(action, "Cannot read frame from camera source.")
                        break

                    now = time.monotonic()
                    with self._lock:
                        runtime = self._cameras[action]
                        runtime.frames_read += 1
                        runtime.last_frame_at = datetime.now().isoformat(timespec="seconds")

                    should_process = now - last_processed >= process_interval
                    should_preview = now - last_preview >= preview_interval
                    if not should_process and not should_preview:
                        continue

                    frame_sequence = 0
                    preview_jpeg = encode_frame_jpeg(frame, preview_quality)
                    if preview_jpeg is not None:
                        frame_sequence = self._publish_preview(
                            action, frame, preview_jpeg
                        )
                        last_preview = now

                    if not should_process:
                        continue
                    last_processed = now

                    try:
                        evidence = encode_frame_data_url(frame)
                        result = process_realtime_frame(
                            frame,
                            action,
                            evidence,
                            session_scope=session_scope,
                        )
                        with self._lock:
                            runtime = self._cameras[action]
                            runtime.frames_processed += 1
                            runtime.last_result = result
                            runtime.last_result_sequence = frame_sequence
                            runtime.last_result_at = datetime.now().isoformat(timespec="seconds")
                            runtime.last_error = None
                    except Exception as exc:
                        self._set_error(action, str(exc))

                if cap:
                    cap.release()
                    cap = None
                with self._lock:
                    self._cameras[action].connected = False
                self._sleep_or_stop(action, reconnect_seconds)
        finally:
            if cap:
                cap.release()
            clear_presence_scope(session_scope)
            with self._frame_condition:
                runtime = self._cameras[action]
                runtime.running = False
                runtime.connected = False
                runtime.latest_jpeg = None
                runtime.frame_width = 0
                runtime.frame_height = 0
                if runtime.session_scope == session_scope:
                    runtime.session_scope = None
                if runtime.thread is threading.current_thread():
                    runtime.thread = None
                self._frame_condition.notify_all()

    def _set_error(self, action: str, message: str) -> None:
        with self._frame_condition:
            runtime = self._cameras[action]
            runtime.connected = False
            runtime.last_error = message
            runtime.latest_jpeg = None
            runtime.frame_width = 0
            runtime.frame_height = 0
            self._frame_condition.notify_all()

    def _sleep_or_stop(self, action: str, seconds: float) -> None:
        self._cameras[action].stop_event.wait(seconds)

    @staticmethod
    def _validate_action(action: str) -> None:
        if action not in VALID_ACTIONS:
            raise ValueError("Invalid camera action.")

    @staticmethod
    def _status_unlocked(runtime: CameraRuntime) -> dict:
        return {
            "action": runtime.action,
            "source": display_camera_source(runtime.source),
            "running": runtime.running,
            "connected": runtime.connected,
            "last_error": runtime.last_error,
            "last_started_at": runtime.last_started_at,
            "last_frame_at": runtime.last_frame_at,
            "last_result_at": runtime.last_result_at,
            "last_result": runtime.last_result,
            "frames_read": runtime.frames_read,
            "frames_processed": runtime.frames_processed,
            "frame_width": runtime.frame_width,
            "frame_height": runtime.frame_height,
            "frame_sequence": runtime.frame_sequence,
            "last_result_sequence": runtime.last_result_sequence,
        }


server_camera_manager = ServerCameraManager()

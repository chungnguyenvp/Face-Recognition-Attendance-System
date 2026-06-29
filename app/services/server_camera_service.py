import base64
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime

import cv2

from app.core.config import settings
from app.db import get_setting
from app.services.realtime_recognition_service import process_realtime_frame


VALID_ACTIONS = {"check_in", "check_out"}


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


def encode_frame_data_url(frame) -> str | None:
    ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        return None
    encoded = base64.b64encode(buffer.tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


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
    thread: threading.Thread | None = field(default=None, repr=False)
    stop_event: threading.Event = field(default_factory=threading.Event, repr=False)


class ServerCameraManager:
    def __init__(self):
        self._cameras = {action: CameraRuntime(action=action) for action in VALID_ACTIONS}
        self._lock = threading.Lock()

    def configured_source(self, action: str) -> str:
        key = "check_out_camera_source" if action == "check_out" else "check_in_camera_source"
        env_source = settings.check_out_camera_source if action == "check_out" else settings.check_in_camera_source
        if str(env_source or "").strip():
            return str(env_source).strip()
        return str(get_setting(key, "") or "").strip()

    def auto_start_enabled(self) -> bool:
        if settings.auto_start_cameras:
            return True
        value = str(get_setting("auto_start_cameras", "false")).lower()
        return value in {"1", "true", "yes", "on"}

    def start_all_configured(self) -> dict:
        statuses = {}
        for action in ("check_in", "check_out"):
            source = self.configured_source(action)
            if source:
                statuses[action] = self.start(action, source)
            else:
                statuses[action] = self.status(action)
        return statuses

    def stop_all(self) -> dict:
        return {action: self.stop(action) for action in ("check_in", "check_out")}

    def start(self, action: str, source: str | None = None) -> dict:
        self._validate_action(action)
        source = source if source is not None else self.configured_source(action)
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
            runtime.stop_event.clear()
            runtime.thread = threading.Thread(
                target=self._run_camera,
                args=(action, parsed_source),
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
            runtime.running = False
            runtime.connected = False
            runtime.thread = None
            return self._status_unlocked(runtime)

    def status(self, action: str | None = None):
        with self._lock:
            if action:
                self._validate_action(action)
                return self._status_unlocked(self._cameras[action])
            return {key: self._status_unlocked(runtime) for key, runtime in self._cameras.items()}

    def _run_camera(self, action: str, source) -> None:
        reconnect_seconds = max(1.0, float(settings.camera_reconnect_seconds))
        process_interval = max(0.05, float(settings.server_camera_process_interval_seconds))
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

                    if now - last_processed < process_interval:
                        continue
                    last_processed = now

                    try:
                        evidence = encode_frame_data_url(frame)
                        result = process_realtime_frame(frame, action, evidence)
                        with self._lock:
                            runtime = self._cameras[action]
                            runtime.frames_processed += 1
                            runtime.last_result = result
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
            with self._lock:
                runtime = self._cameras[action]
                runtime.running = False
                runtime.connected = False
                if runtime.thread is threading.current_thread():
                    runtime.thread = None

    def _set_error(self, action: str, message: str) -> None:
        with self._lock:
            runtime = self._cameras[action]
            runtime.connected = False
            runtime.last_error = message

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
            "source": runtime.source,
            "running": runtime.running,
            "connected": runtime.connected,
            "last_error": runtime.last_error,
            "last_started_at": runtime.last_started_at,
            "last_frame_at": runtime.last_frame_at,
            "last_result_at": runtime.last_result_at,
            "last_result": runtime.last_result,
            "frames_read": runtime.frames_read,
            "frames_processed": runtime.frames_processed,
        }


server_camera_manager = ServerCameraManager()

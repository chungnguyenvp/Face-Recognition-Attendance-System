import base64
import os
from datetime import datetime
from uuid import uuid4

from app.db import get_db
from app.repositories import access_log_repository, alert_repository
from app.services.private_storage import PRIVATE_EVIDENCE_DIR, evidence_relative_path


EVIDENCE_DIR = str(PRIVATE_EVIDENCE_DIR)


def seconds_since_last_success(student_id: int, action: str) -> float | None:
    with get_db() as db:
        row = access_log_repository.get_last_success_created_at(db, student_id, action)
    if not row or not row["created_at"]:
        return None
    try:
        created_at = datetime.fromisoformat(row["created_at"])
    except ValueError:
        return None
    return max(0.0, (datetime.now() - created_at).total_seconds())


def save_evidence_image(image_data: str | None) -> str | None:
    if not image_data:
        return None
    try:
        payload = image_data.split(",", 1)[1] if "," in image_data else image_data
        image_bytes = base64.b64decode(payload)
    except Exception:
        return None

    now = datetime.now()
    day = now.strftime("%Y%m%d")
    folder = os.path.join(EVIDENCE_DIR, day)
    os.makedirs(folder, exist_ok=True)
    filename = f"{now.strftime('%H%M%S')}_{uuid4().hex[:10]}.jpg"
    file_path = os.path.join(folder, filename)
    with open(file_path, "wb") as file_obj:
        file_obj.write(image_bytes)
    return evidence_relative_path(day, filename)


def log_access(
    student,
    action: str,
    result: str,
    confidence=None,
    note=None,
    evidence_image_path=None,
    on_success=None,
) -> None:
    created_at = datetime.now()
    with get_db() as db:
        access_log_repository.create_access_log(
            db,
            student.get("student_id") if student else None,
            student.get("student_code") if student else "Unknown",
            student.get("full_name") if student else "Unknown",
            action,
            result,
            confidence,
            note,
            evidence_image_path,
            created_at.isoformat(timespec="seconds"),
        )
    if result == "success" and on_success:
        on_success(student, action, created_at)


def create_alert(alert_type: str, message: str, evidence_image_path=None, event_date: str | None = None) -> None:
    created_at = datetime.now()
    with get_db() as db:
        alert_repository.create_alert(
            db,
            alert_type,
            message,
            evidence_image_path,
            event_date or created_at.date().isoformat(),
            created_at.isoformat(timespec="seconds"),
        )

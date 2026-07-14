from app.core.config import settings
from app.db import get_db, get_setting
from app.repositories import student_face_repository
from app.services.attendance_service import can_log, can_log_event
from app.ai.embedding_cache import face_embedding_cache
from app.ai.face_engine import face_service
from app.services.realtime_access_service import (
    create_alert,
    log_access,
    save_evidence_image,
    seconds_since_last_success,
    validate_attendance_transition,
)
from app.services.realtime_session_service import (
    DEFAULT_SESSION_SCOPE,
    apply_denied_item,
    apply_recent_duplicate_item,
    cleanup_presence_sessions,
    face_area,
    liveness_history_note,
    build_session_key,
    session_decision,
    spoof_alert_message,
)


WARNING_LOG_COOLDOWN_SECONDS = 10
INVALID_TRANSITION_GRACE_SECONDS = 10


def load_known_faces():
    with get_db() as db:
        rows = student_face_repository.list_active_face_embeddings(db)
    known = []
    for row in rows:
        known.append(
            {
                "student_id": row["student_id"],
                "student_code": row["student_code"],
                "full_name": row["full_name"],
                "embedding": face_service.deserialize_embedding(row["embedding"]),
            }
        )
    return known


def realtime_face_min_size(setting_getter=get_setting) -> int:
    try:
        return int(setting_getter("liveness_min_face_size", settings.liveness_min_face_size))
    except (TypeError, ValueError):
        return int(settings.liveness_min_face_size)


def is_actionable_realtime_face(item: dict, min_size: int | None = None, setting_getter=get_setting) -> bool:
    bbox = item.get("bbox") or []
    if len(bbox) < 4:
        return False
    x1, y1, x2, y2 = [float(value) for value in bbox[:4]]
    face_w = max(0.0, x2 - x1)
    face_h = max(0.0, y2 - y1)
    required_size = realtime_face_min_size(setting_getter) if min_size is None else min_size
    return face_w >= required_size and face_h >= required_size


def apply_secondary_display_item(item: dict, note: str | None = None) -> None:
    item["decision"] = "secondary"
    item["session_state"] = "secondary"
    item["display_status"] = "secondary"
    item["display_full_name"] = item.get("full_name")
    item["display_student_code"] = item.get("student_code")
    item["logged"] = False
    if note:
        item["note"] = note


def process_realtime_frame(
    image,
    action: str,
    evidence_image_data: str | None = None,
    setting_getter=get_setting,
    known_faces_loader=load_known_faces,
    recognize_faces=None,
    cleanup_sessions=cleanup_presence_sessions,
    decide_session=session_decision,
    session_scope: str = DEFAULT_SESSION_SCOPE,
) -> dict:
    threshold = float(setting_getter("face_threshold", 0.55))
    cooldown = int(setting_getter("check_cooldown_seconds", 30))
    active_action = action if action in {"check_in", "check_out"} else "check_in"
    known = face_embedding_cache.get_known_faces(known_faces_loader)
    recognizer = recognize_faces or face_service.recognize_faces
    results = recognizer(image, known, threshold)

    actionable_results = []
    for item in results:
        if is_actionable_realtime_face(item, setting_getter=setting_getter):
            actionable_results.append(item)
        else:
            apply_secondary_display_item(item, "Khuon mat qua nho, khong dung de diem danh.")

    evidence_image_path = None

    def get_evidence_image_path():
        nonlocal evidence_image_path
        if evidence_image_path is None:
            evidence_image_path = save_evidence_image(evidence_image_data)
        return evidence_image_path

    seen_session_keys = set()
    primary_item = max(actionable_results, key=face_area, default=None)
    if len(actionable_results) > 1:
        for item in actionable_results:
            if item is primary_item:
                item["decision"] = "denied"
                item["session_state"] = "denied"
                item["display_status"] = "denied"
                item["warning_type"] = "multiple_faces"
                item["note"] = "Chi nen co 1 nguoi trong khung hinh de diem danh."
                item["display_full_name"] = item.get("full_name")
                item["display_student_code"] = item.get("student_code")
                item["logged"] = False
            else:
                apply_secondary_display_item(item)
        cleanup_sessions(seen_session_keys, session_scope)
        return {"type": "result", "action": active_action, "items": results}

    for item in actionable_results:
        if item is not primary_item:
            apply_secondary_display_item(item)
            continue

        if item.get("recognized") and item.get("student_id"):
            transition_ok, transition_note = validate_attendance_transition(item["student_id"], active_action)
            if not transition_ok:
                current_session_key = build_session_key(active_action, item, session_scope)
                seen_session_keys.add(current_session_key)
                event_key = f"invalid_transition:{active_action}:{item['student_id']}"

                last_success_age = seconds_since_last_success(item["student_id"], active_action)
                if last_success_age is not None and last_success_age < INVALID_TRANSITION_GRACE_SECONDS:
                    apply_recent_duplicate_item(item, transition_note)
                    continue

                if not can_log_event(event_key, WARNING_LOG_COOLDOWN_SECONDS):
                    apply_recent_duplicate_item(item, transition_note)
                    continue

                apply_denied_item(item, transition_note)
                evidence_path = get_evidence_image_path()
                log_access(item, active_action, "denied", item.get("confidence"), transition_note, evidence_path)
                item["logged"] = True
                item["evidence_image_path"] = evidence_path
                continue

        decision, current_session_key, display_status = decide_session(
            active_action, item, session_scope
        )
        seen_session_keys.add(current_session_key)
        item["decision"] = decision or "pending"
        item["session_state"] = display_status
        item["display_status"] = display_status
        if decision is None:
            item["logged"] = False
            continue

        if decision == "denied":
            note = item.get("note") or "Phat hien nghi ngo dung anh/man hinh de gia mao."
            note = note + liveness_history_note(item)
            alert_message = spoof_alert_message(item)
            student_key = item.get("student_id") or "unknown"
            event_key = f"denied:{active_action}:{student_key}"
            if can_log_event(event_key, WARNING_LOG_COOLDOWN_SECONDS):
                evidence_path = get_evidence_image_path()
                log_access(item if item.get("student_id") else None, active_action, "denied", item.get("confidence"), note, evidence_path)
                create_alert("spoof_detected", alert_message, evidence_path)
                item["logged"] = True
                item["evidence_image_path"] = evidence_path
            else:
                item["logged"] = False
                item["note"] = "Cooldown: khong ghi canh bao gia mao qua gan."
            continue

        if decision == "success":
            if can_log(item["student_id"], active_action, cooldown):
                evidence_path = get_evidence_image_path()
                log_access(item, active_action, "success", item["confidence"], "Camera realtime", evidence_path)
                item["logged"] = True
                item["evidence_image_path"] = evidence_path
            else:
                item["logged"] = False
                item["note"] = "Cooldown: khong ghi log trung qua gan."
        elif decision == "warning":
            event_key = f"unknown:{active_action}"
            if can_log_event(event_key, WARNING_LOG_COOLDOWN_SECONDS):
                evidence_path = get_evidence_image_path()
                log_access(None, active_action, "warning", item.get("confidence"), "Khuon mat la", evidence_path)
                create_alert("unknown_face", "Phat hien khuon mat la tu camera realtime.", evidence_path)
                item["logged"] = True
                item["evidence_image_path"] = evidence_path
            else:
                item["logged"] = False
                item["note"] = "Cooldown: khong ghi canh bao khuon mat la qua gan."

    cleanup_sessions(seen_session_keys, session_scope)
    return {"type": "result", "action": active_action, "items": results}

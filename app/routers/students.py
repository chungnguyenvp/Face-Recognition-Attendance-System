import sqlite3
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.config import settings
from app.db import get_db, get_setting, row_to_dict
from app.repositories import (
    leave_repository,
    student_face_repository,
    student_repository,
    user_repository,
)
from app.routers.deps import require_admin, require_admin_or_lab_manager
from app.schemas.students import StudentCreate, StudentUpdate, StudentWorkTimeUpdate
from app.services.attendance_service import recalculate_student_attendance_records
from app.services.audit_service import audit_diff, write_audit_log
from app.ai.embedding_cache import face_embedding_cache
from app.services.student_face_service import (
    MAX_FACE_EMBEDDINGS_PER_STUDENT,
    delete_face_image_files as _delete_face_image_files,
    delete_student_faces as _delete_student_faces,
)
from app.services.session_service import revoke_user_sessions

router = APIRouter(prefix="/api/students", tags=["students"])


@router.get("", dependencies=[Depends(require_admin_or_lab_manager)])
def list_students(q: str = ""):
    default_start = get_setting("work_start_time", settings.work_start_time)
    default_end = get_setting("work_end_time", settings.work_end_time)
    with get_db() as db:
        rows = student_repository.list_active_students(db, q, default_start, default_end)
    return {"items": [row_to_dict(r) for r in rows], "max_faces": MAX_FACE_EMBEDDINGS_PER_STUDENT}


@router.post("")
def create_student(payload: StudentCreate, request: Request, actor=Depends(require_admin_or_lab_manager)):
    try:
        with get_db() as db:
            student_id = student_repository.create_student(
                db,
                payload.student_code,
                payload.full_name,
                payload.class_name,
                payload.status,
                datetime.now().isoformat(timespec="seconds"),
            )
            write_audit_log(
                db,
                actor,
                "students.create",
                "student",
                student_id,
                f"{payload.student_code} - {payload.full_name}",
                {
                    "student_code": payload.student_code,
                    "full_name": payload.full_name,
                    "class_name": payload.class_name,
                    "status": payload.status,
                },
                request,
            )
        return {"ok": True, "id": student_id}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Mã sinh viên đã tồn tại.")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Không tạo được sinh viên: {exc}")


@router.get("/{student_id}", dependencies=[Depends(require_admin_or_lab_manager)])
def get_student(student_id: int):
    with get_db() as db:
        student = student_repository.get_student_by_id(db, student_id)
        faces = student_face_repository.list_student_faces(db, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Không tìm thấy sinh viên.")
    return {
        "student": row_to_dict(student),
        "faces": [row_to_dict(f) for f in faces],
        "face_count": len(faces),
        "max_faces": MAX_FACE_EMBEDDINGS_PER_STUDENT,
    }


@router.put("/{student_id}")
def update_student(student_id: int, payload: StudentUpdate, request: Request, actor=Depends(require_admin_or_lab_manager)):
    image_paths = []
    invalidate_face_cache = False
    with get_db() as db:
        student = student_repository.get_student_by_id(db, student_id)
        if not student:
            raise HTTPException(status_code=404, detail="Không tìm thấy sinh viên.")
        new_status = payload.status
        student_repository.update_student_profile(
            db,
            student_id,
            payload.student_code,
            payload.full_name,
            payload.class_name,
            new_status,
        )
        if new_status != "active":
            image_paths = _delete_student_faces(db, student_id)
        before = row_to_dict(student)
        after = {
            **before,
            "student_code": payload.student_code,
            "full_name": payload.full_name,
            "class_name": payload.class_name,
            "status": new_status,
        }
        changes = audit_diff(before, after, ["student_code", "full_name", "class_name", "status"])
        invalidate_face_cache = any(key in changes for key in ("student_code", "full_name", "status"))
        if changes:
            write_audit_log(
                db,
                actor,
                "students.update",
                "student",
                student_id,
                f"{payload.student_code} - {payload.full_name}",
                {"changes": changes, "deleted_face_count": len(image_paths)},
                request,
            )
    if invalidate_face_cache:
        face_embedding_cache.invalidate()
    _delete_face_image_files(image_paths)
    return {"ok": True, "deleted_face_count": len(image_paths)}


@router.put("/{student_id}/work-time")
def update_student_work_time(student_id: int, payload: StudentWorkTimeUpdate, request: Request, actor=Depends(require_admin_or_lab_manager)):
    with get_db() as db:
        student = student_repository.get_student_identity(db, student_id)
        if not student:
            raise HTTPException(status_code=404, detail="Không tìm thấy sinh viên.")
        before = student_repository.get_student_work_time(db, student_id)
        student_repository.upsert_student_work_time(
            db,
            student_id,
            payload.work_start_time,
            payload.work_end_time,
            datetime.now().isoformat(timespec="seconds"),
        )
        changes = audit_diff(
            row_to_dict(before) or {},
            {"work_start_time": payload.work_start_time, "work_end_time": payload.work_end_time},
            ["work_start_time", "work_end_time"],
        )
        if changes:
            write_audit_log(
                db,
                actor,
                "students.work_time.update",
                "student",
                student_id,
                f"{student['student_code']} - {student['full_name']}",
                {"changes": changes},
                request,
            )
    updated = recalculate_student_attendance_records(student_id)
    return {"ok": True, "updated": updated}


@router.delete("/{student_id}/work-time")
def reset_student_work_time(student_id: int, request: Request, actor=Depends(require_admin_or_lab_manager)):
    with get_db() as db:
        student = student_repository.get_student_identity(db, student_id)
        if not student:
            raise HTTPException(status_code=404, detail="Không tìm thấy sinh viên.")
        before = student_repository.get_student_work_time(db, student_id)
        student_repository.delete_student_work_time(db, student_id)
        if before:
            write_audit_log(
                db,
                actor,
                "students.work_time.reset",
                "student",
                student_id,
                f"{student['student_code']} - {student['full_name']}",
                {"previous": row_to_dict(before)},
                request,
            )
    updated = recalculate_student_attendance_records(student_id)
    return {"ok": True, "updated": updated}


@router.delete("/{student_id}")
def delete_student(student_id: int, request: Request, actor=Depends(require_admin)):
    with get_db() as db:
        student = student_repository.get_student_by_id(db, student_id)
        if student and leave_repository.student_has_leave_history(db, student_id):
            raise HTTPException(status_code=409, detail="Khong the xoa sinh vien da co lich su don nghi. Hay chuyen sinh vien sang inactive.")
        if not student:
            raise HTTPException(status_code=404, detail="Không tìm thấy sinh viên.")
        linked_user = user_repository.get_student_user_by_student_id(db, student_id)
        if linked_user:
            user_repository.update_user_status(db, linked_user["id"], "inactive")
            revoke_user_sessions(db, linked_user["id"])
        student_repository.clear_student_access_log_links(db, student_id)
        student_repository.delete_student_work_time(db, student_id)
        student_repository.delete_student_attendance_records(db, student_id)
        image_paths = _delete_student_faces(db, student_id)
        student_repository.delete_student_by_id(db, student_id)
        write_audit_log(
            db,
            actor,
            "students.delete",
            "student",
            student_id,
            f"{student['student_code']} - {student['full_name']}",
            {
                "student_code": student["student_code"],
                "full_name": student["full_name"],
                "class_name": student["class_name"],
                "status": student["status"],
                "deleted_face_count": len(image_paths),
                "linked_user_id": linked_user["id"] if linked_user else None,
                "linked_user_deactivated": bool(linked_user),
                "linked_user_sessions_revoked": bool(linked_user),
            },
            request,
        )
    face_embedding_cache.invalidate()
    _delete_face_image_files(image_paths)
    return {
        "ok": True,
        "linked_user_deactivated": bool(linked_user),
    }

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.security import hash_password
from app.db import get_db, row_to_dict
from app.repositories import user_repository
from app.routers.deps import ADMIN_ROLE, LAB_MANAGER_ROLE, STUDENT_ROLE, require_admin_or_lab_manager
from app.schemas.users import UserCreate, UserUpdate
from app.services.audit_service import audit_diff, write_audit_log
from app.services.session_service import revoke_user_sessions

router = APIRouter(prefix="/api/users", tags=["users"])


def _is_lab_manager(user: dict) -> bool:
    return user.get("role") == LAB_MANAGER_ROLE


def _validate_student_link(db, student_id: int | None) -> None:
    if not student_id:
        raise HTTPException(status_code=400, detail="Tài khoản sinh viên phải liên kết với hồ sơ sinh viên.")
    if not user_repository.student_exists(db, student_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy sinh viên để liên kết.")


@router.get("")
def list_users(actor=Depends(require_admin_or_lab_manager)):
    role_filter = None
    if _is_lab_manager(actor):
        # Lab Manager chỉ xem/quản lý tài khoản sinh viên, không xem tài khoản admin khác.
        role_filter = STUDENT_ROLE
    with get_db() as db:
        rows = user_repository.list_users_with_students(db, role_filter)
    return {"items": [row_to_dict(r) for r in rows], "current_role": actor.get("role")}


@router.post("")
def create_user(payload: UserCreate, request: Request, actor=Depends(require_admin_or_lab_manager)):
    if _is_lab_manager(actor) and payload.role != STUDENT_ROLE:
        raise HTTPException(status_code=403, detail="Quản lý phòng lab chỉ được tạo tài khoản sinh viên.")
    if payload.role == STUDENT_ROLE and not payload.student_id:
        raise HTTPException(status_code=400, detail="Tài khoản sinh viên phải liên kết với hồ sơ sinh viên.")
    if payload.role in {ADMIN_ROLE, LAB_MANAGER_ROLE} and payload.student_id:
        raise HTTPException(status_code=400, detail="Tài khoản admin/lab_manager không cần student_id.")
    try:
        with get_db() as db:
            if payload.role == STUDENT_ROLE:
                _validate_student_link(db, payload.student_id)
            user_id = user_repository.create_user(
                db,
                payload.username.strip(),
                hash_password(payload.password),
                payload.role,
                payload.student_id if payload.role == STUDENT_ROLE else None,
                datetime.now().isoformat(timespec="seconds"),
            )
            row = user_repository.get_user_public(db, user_id)
            write_audit_log(
                db,
                actor,
                "users.create",
                "user",
                row["id"],
                f"{row['username']} ({row['role']})",
                {
                    "username": row["username"],
                    "role": row["role"],
                    "student_id": row["student_id"],
                    "status": row["status"],
                },
                request,
            )
    except HTTPException:
        raise
    except Exception as exc:
        message = str(exc).lower()
        if "unique" in message:
            raise HTTPException(status_code=409, detail="Username hoặc sinh viên này đã có tài khoản.")
        raise
    return {"ok": True, "item": row_to_dict(row)}


@router.put("/{user_id}")
def update_user(user_id: int, payload: UserUpdate, request: Request, actor=Depends(require_admin_or_lab_manager)):
    try:
        with get_db() as db:
            current = user_repository.get_user_by_id(db, user_id)
            if not current:
                raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")
            if _is_lab_manager(actor) and current["role"] != STUDENT_ROLE:
                raise HTTPException(status_code=403, detail="Quản lý phòng lab chỉ được sửa tài khoản sinh viên.")
            if payload.student_id is not None:
                if current["role"] != STUDENT_ROLE:
                    raise HTTPException(status_code=400, detail="Chỉ tài khoản student mới được liên kết student_id.")
                _validate_student_link(db, payload.student_id)
                user_repository.update_user_student_id(db, user_id, payload.student_id)
            if payload.password:
                user_repository.update_user_password_hash(db, user_id, hash_password(payload.password))
            if payload.status:
                if current["role"] == ADMIN_ROLE and payload.status != "active":
                    active_admin_count = user_repository.count_active_admins(db, exclude_user_id=user_id)
                    if active_admin_count <= 0:
                        raise HTTPException(status_code=400, detail="Không được khóa admin active cuối cùng.")
                user_repository.update_user_status(db, user_id, payload.status)
            sessions_revoked = bool(payload.password or payload.status == "inactive")
            if sessions_revoked:
                revoke_user_sessions(db, user_id)
            row = user_repository.get_user_public(db, user_id)
            before = row_to_dict(current)
            after = row_to_dict(row)
            changes = audit_diff(before, after, ["student_id", "status"])
            if payload.password:
                changes["password_changed"] = True
            if sessions_revoked:
                changes["sessions_revoked"] = True
            if changes:
                write_audit_log(
                    db,
                    actor,
                    "users.update",
                    "user",
                    row["id"],
                    f"{row['username']} ({row['role']})",
                    {"changes": changes},
                    request,
                )
    except HTTPException:
        raise
    except Exception as exc:
        if "unique" in str(exc).lower():
            raise HTTPException(status_code=409, detail="Sinh viên này đã có tài khoản khác.")
        raise
    return {"ok": True, "item": row_to_dict(row)}


@router.delete("/{user_id}")
def delete_user(user_id: int, request: Request, actor=Depends(require_admin_or_lab_manager)):
    with get_db() as db:
        current = user_repository.get_user_delete_summary(db, user_id)
        if not current:
            raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")
        if _is_lab_manager(actor) and current["role"] != STUDENT_ROLE:
            raise HTTPException(status_code=403, detail="Quản lý phòng lab chỉ được xóa tài khoản sinh viên.")
        admin_count = user_repository.count_active_admins(db)
        if current["role"] == ADMIN_ROLE and admin_count <= 1:
            raise HTTPException(status_code=400, detail="Không được xóa admin active cuối cùng.")
        revoke_user_sessions(db, user_id)
        user_repository.delete_user(db, user_id)
        write_audit_log(
            db,
            actor,
            "users.delete",
            "user",
            current["id"],
            f"{current['username']} ({current['role']})",
            {
                "username": current["username"],
                "role": current["role"],
                "student_id": current["student_id"],
                "status": current["status"],
            },
            request,
        )
    return {"ok": True}

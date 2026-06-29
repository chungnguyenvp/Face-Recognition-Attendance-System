from fastapi import APIRouter, Depends
from app.db import get_db, row_to_dict
from app.repositories import student_portal_repository
from app.routers.deps import require_student
from app.routers.students import MAX_FACE_EMBEDDINGS_PER_STUDENT
from app.services.attendance_service import attendance_record_context, ensure_attendance_records

router = APIRouter(prefix="/api/student", tags=["student"], dependencies=[Depends(require_student)])


def _current_student(user):
    with get_db() as db:
        student = student_portal_repository.get_student_profile(db, user["student_id"])
    return row_to_dict(student)


@router.get("/me")
def student_me(user=Depends(require_student)):
    return {"user": user, "student": _current_student(user)}


@router.get("/faces")
def my_registered_faces(user=Depends(require_student)):
    with get_db() as db:
        rows = student_portal_repository.list_registered_faces(db, user["student_id"])
    items = [row_to_dict(row) for row in rows]
    latest_update = items[0]["created_at"] if items else None
    return {
        "items": items,
        "count": len(items),
        "max_faces": MAX_FACE_EMBEDDINGS_PER_STUDENT,
        "latest_update": latest_update,
    }


@router.get("/access-logs")
def my_access_logs(
    limit: int = 100,
    date_from: str | None = None,
    date_to: str | None = None,
    action: str | None = None,
    result: str | None = None,
    user=Depends(require_student),
):
    with get_db() as db:
        rows = student_portal_repository.list_access_logs(
            db,
            user["student_id"],
            limit,
            date_from,
            date_to,
            action,
            result,
        )
    return {"items": [row_to_dict(r) for r in rows], "count": len(rows)}


@router.get("/attendance-records")
def my_attendance_records(
    limit: int = 100,
    date_from: str | None = None,
    date_to: str | None = None,
    status: str | None = None,
    user=Depends(require_student),
):
    ensure_attendance_records()
    with get_db() as db:
        rows = student_portal_repository.list_attendance_records(
            db,
            user["student_id"],
            limit,
            date_from,
            date_to,
            status,
        )
        items = []
        for row in rows:
            item = row_to_dict(row)
            context = attendance_record_context(db, item["student_id"], item["attendance_date"])
            item.update(context)
            items.append(item)
    return {"items": items, "count": len(items)}

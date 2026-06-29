from fastapi import APIRouter, Depends

from app.db import get_db, row_to_dict
from app.repositories import dashboard_repository
from app.routers.deps import require_admin_or_lab_manager
from app.services.attendance_service import ensure_attendance_records

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard", dependencies=[Depends(require_admin_or_lab_manager)])
def dashboard():
    ensure_attendance_records()
    with get_db() as db:
        total_students = dashboard_repository.count_students(db)
        active_students = dashboard_repository.count_active_students(db)
        face_registered = dashboard_repository.count_active_students_with_faces(db)
        checkin_today = dashboard_repository.count_success_access_logs_today(db, "check_in")
        checkout_today = dashboard_repository.count_success_access_logs_today(db, "check_out")
        alerts_today = dashboard_repository.count_alerts_today(db)
        on_time_today = dashboard_repository.count_attendance_records_today(db, ("present_on_time",))
        late_today = dashboard_repository.count_attendance_records_today(db, ("late", "late_and_early_leave"))
        absent_today = dashboard_repository.count_attendance_records_today(db, ("absent",))
        missing_checkout_today = dashboard_repository.count_attendance_records_today(db, ("missing_checkout",))
        recent = dashboard_repository.list_recent_access_logs(db)
    return {
        "stats": {
            "total_students": total_students,
            "active_students": active_students,
            "face_registered": face_registered,
            "not_registered": max(total_students - face_registered, 0),
            "checkin_today": checkin_today,
            "checkout_today": checkout_today,
            "alerts_today": alerts_today,
            "on_time_today": on_time_today,
            "late_today": late_today,
            "absent_today": absent_today,
            "missing_checkout_today": missing_checkout_today,
        },
        "recent_logs": [row_to_dict(r) for r in recent],
    }

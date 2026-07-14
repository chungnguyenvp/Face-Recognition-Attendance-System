import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from app.core.csrf import csrf_protect_middleware
from app.core.config import settings
from app.core.lifespan import lifespan
from app.core.middleware import security_headers_middleware
from app.routers import (
    access_logs,
    alerts,
    attendance,
    audit_logs,
    auth,
    dashboard,
    face_registration_requests,
    files,
    health,
    leave_requests,
    pages,
    server_cameras,
    settings as settings_router,
    student_portal,
    student_reports,
    student_faces,
    students,
    users,
    work_schedule,
)


def _csv_setting(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _docs_url(path: str) -> str | None:
    return path if settings.public_docs_enabled else None


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
    docs_url=_docs_url("/docs"),
    redoc_url=_docs_url("/redoc"),
    openapi_url=_docs_url("/openapi.json"),
)
trusted_hosts = _csv_setting(settings.trusted_hosts)
if trusted_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts)
app.middleware("http")(security_headers_middleware)
app.middleware("http")(csrf_protect_middleware)

app.mount("/static", StaticFiles(directory="web/static"), name="static")

app.include_router(auth.router)
app.include_router(students.router)
app.include_router(student_faces.router)
app.include_router(face_registration_requests.student_router)
app.include_router(face_registration_requests.staff_router)
app.include_router(access_logs.router)
app.include_router(alerts.router)
app.include_router(attendance.router)
app.include_router(audit_logs.router)
app.include_router(dashboard.router)
app.include_router(files.router)
app.include_router(health.router)
app.include_router(leave_requests.student_router)
app.include_router(leave_requests.staff_router)
app.include_router(pages.router)
app.include_router(settings_router.router)
app.include_router(server_cameras.router)
app.include_router(users.router)
app.include_router(student_portal.router)
app.include_router(student_reports.student_router)
app.include_router(student_reports.staff_router)
app.include_router(work_schedule.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8002, reload=True)

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.db import init_db
from app.services.attendance_service import mark_missing_checkouts
from app.ai.face_engine import face_service
from app.ai.liveness_engine import liveness_service
from app.services.server_camera_service import server_camera_manager
from app.workers.missing_checkout_worker import missing_checkout_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    created = mark_missing_checkouts()
    if created:
        print(f"Created {created} missing checkout alert(s) on startup.")
    missing_checkout_task = asyncio.create_task(missing_checkout_scheduler())
    face_service.load()
    liveness_service.load()
    if server_camera_manager.auto_start_enabled():
        server_camera_manager.start_all_configured()
    try:
        yield
    finally:
        server_camera_manager.stop_all()
        missing_checkout_task.cancel()
        with suppress(asyncio.CancelledError):
            await missing_checkout_task

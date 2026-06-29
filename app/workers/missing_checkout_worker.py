import asyncio

from app.core.config import settings
from app.db import get_setting
from app.services.attendance_service import mark_missing_checkouts


async def missing_checkout_scheduler():
    while True:
        try:
            created = mark_missing_checkouts()
            if created:
                print(f"Created {created} missing checkout alert(s).")
            interval = int(get_setting("missing_checkout_scan_interval_seconds", settings.missing_checkout_scan_interval_seconds))
        except Exception as exc:
            print(f"Missing checkout scheduler error: {exc}")
            interval = settings.missing_checkout_scan_interval_seconds
        await asyncio.sleep(max(30, interval))

from fastapi import APIRouter, Depends

from app.db import get_db, row_to_dict
from app.repositories import audit_log_repository
from app.routers.deps import require_admin


router = APIRouter(prefix="/api/audit-logs", tags=["audit_logs"])


@router.get("", dependencies=[Depends(require_admin)])
def audit_logs(
    limit: int = 200,
    date_from: str | None = None,
    date_to: str | None = None,
    actor: str | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    q: str | None = None,
):
    with get_db() as db:
        rows = audit_log_repository.list_audit_logs(db, limit, date_from, date_to, actor, action, entity_type, q)
    return {"items": [row_to_dict(row) for row in rows], "count": len(rows)}

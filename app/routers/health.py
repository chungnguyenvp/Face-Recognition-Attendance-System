from fastapi import APIRouter

from app.core.config import settings
from app.ai.face_engine import face_service
from app.ai.liveness_engine import liveness_service


router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    if not settings.health_details_enabled:
        return {"ok": True}
    return {
        "ok": True,
        "face_model_loaded": face_service.loaded,
        "face_model_error": face_service.load_error,
        "liveness_enabled": liveness_service.is_enabled(),
        "liveness_threshold": liveness_service.threshold(),
        "liveness_real_class_index": liveness_service.real_class_index(),
        "liveness_crop_scale": liveness_service.crop_scale(),
        "liveness_model_loaded": liveness_service.loaded,
        "liveness_model_error": liveness_service.load_error,
    }

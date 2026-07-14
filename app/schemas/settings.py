from pydantic import BaseModel, Field, field_validator

from app.core.time_utils import validate_time_text


class SettingsUpdate(BaseModel):
    face_threshold: float = Field(ge=0, le=1)
    check_cooldown_seconds: int = Field(ge=1)
    frame_skip: int = Field(ge=1)
    liveness_enabled: bool | None = None
    missing_checkout_cutoff_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    work_start_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    work_end_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    late_grace_minutes: int | None = Field(default=None, ge=0, le=240)
    early_leave_grace_minutes: int | None = Field(default=None, ge=0, le=240)

    @field_validator("missing_checkout_cutoff_time", "work_start_time", "work_end_time")
    @classmethod
    def validate_time_value(cls, value: str | None) -> str | None:
        return validate_time_text(value)

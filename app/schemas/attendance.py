from pydantic import BaseModel, Field


class AttendanceRecalculateRequest(BaseModel):
    date_from: str | None = None
    date_to: str | None = None


class MissingCheckoutResolutionRequest(BaseModel):
    resolution_type: str
    checkout_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    reason: str

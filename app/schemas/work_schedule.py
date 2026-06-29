from datetime import date, time
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.time_utils import validate_time_text


class WorkScheduleUpdate(BaseModel):
    effective_from: date | None = None
    monday_enabled: bool = True
    tuesday_enabled: bool = True
    wednesday_enabled: bool = True
    thursday_enabled: bool = True
    friday_enabled: bool = True
    saturday_enabled: bool = False
    sunday_enabled: bool = False
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    late_allowed_minutes: int = Field(ge=0, le=240)
    early_leave_allowed_minutes: int = Field(ge=0, le=240)
    checkout_cutoff_time: str = Field(pattern=r"^\d{2}:\d{2}$")

    @field_validator("start_time", "end_time", "checkout_cutoff_time")
    @classmethod
    def validate_time_value(cls, value: str) -> str:
        return validate_time_text(value) or value

    @model_validator(mode="after")
    def validate_time_order(self):
        start, end, cutoff = (time.fromisoformat(item) for item in (self.start_time, self.end_time, self.checkout_cutoff_time))
        if start >= end:
            raise ValueError("Giờ kết thúc phải sau giờ bắt đầu.")
        if cutoff <= end:
            raise ValueError("Giờ chốt thiếu check-out phải sau giờ kết thúc.")
        return self


class CalendarExceptionCreate(BaseModel):
    exception_date: date
    exception_type: Literal["off", "working"] = "off"
    holiday_name: str = Field(min_length=2, max_length=120)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("holiday_name", "note")
    @classmethod
    def trim_text(cls, value: str | None) -> str | None:
        return value.strip() if value else value


class CalendarExceptionUpdate(CalendarExceptionCreate):
    pass

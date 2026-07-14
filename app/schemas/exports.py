from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


AttendanceExportStatus = Literal[
    "present_on_time",
    "late",
    "early_leave",
    "late_and_early_leave",
    "missing_checkout",
    "absent",
    "leave_approved",
    "leave_pending",
    "pending",
    "unfinalized",
    "off_day",
]


class AttendanceExportRequest(BaseModel):
    date_from: date
    date_to: date
    status: AttendanceExportStatus | None = None
    q: str | None = Field(default=None, max_length=120)
    include_summary: bool = True
    include_details: bool = True

    @field_validator("q")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        value = (value or "").strip()
        return value or None

    @model_validator(mode="after")
    def validate_export_options(self):
        if self.date_to < self.date_from:
            raise ValueError("Ngày kết thúc không được trước ngày bắt đầu.")
        if (self.date_to - self.date_from).days > 365:
            raise ValueError("Mỗi báo cáo chỉ được xuất tối đa 366 ngày.")
        if not self.include_summary and not self.include_details:
            raise ValueError("Phải chọn ít nhất một trang Tổng hợp hoặc Chi tiết.")
        return self

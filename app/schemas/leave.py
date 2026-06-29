from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


LeaveType = Literal["sick", "personal", "study", "family", "other"]
LeaveStatus = Literal["pending", "approved", "rejected", "cancelled", "revoked"]


class LeaveRequestCreate(BaseModel):
    leave_type: LeaveType
    start_date: date
    end_date: date
    reason: str = Field(min_length=5, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        value = (value or "").strip()
        if len(value) < 5:
            raise ValueError("Ly do nghi phai co it nhat 5 ky tu.")
        return value

    @field_validator("end_date")
    @classmethod
    def validate_date_range(cls, end_date: date, info) -> date:
        start_date = info.data.get("start_date")
        if start_date and end_date < start_date:
            raise ValueError("Ngay ket thuc khong duoc truoc ngay bat dau.")
        return end_date


class LeaveRequestApprove(BaseModel):
    reviewer_note: str | None = Field(default=None, max_length=500)

    @field_validator("reviewer_note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        value = (value or "").strip()
        return value or None


class LeaveRequestReject(BaseModel):
    reviewer_note: str = Field(min_length=3, max_length=500)

    @field_validator("reviewer_note")
    @classmethod
    def validate_note(cls, value: str) -> str:
        value = (value or "").strip()
        if len(value) < 3:
            raise ValueError("Can nhap ly do tu choi.")
        return value


class LeaveRequestRevoke(LeaveRequestReject):
    pass

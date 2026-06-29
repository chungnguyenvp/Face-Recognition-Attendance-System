from typing import Literal

from pydantic import BaseModel, Field, field_validator


ReportStatus = Literal["revision_requested", "approved"]


class ReportReview(BaseModel):
    status: ReportStatus
    comment: str | None = Field(default=None, max_length=2_000)

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        value = (value or "").strip()
        return value or None

    def validate_review(self) -> None:
        if self.status == "revision_requested" and (not self.comment or len(self.comment) < 3):
            raise ValueError("Can nhap nhan xet it nhat 3 ky tu khi yeu cau chinh sua.")

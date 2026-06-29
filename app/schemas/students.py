from pydantic import BaseModel, Field, field_validator

from app.core.time_utils import validate_time_text


class StudentCreate(BaseModel):
    student_code: str
    full_name: str
    class_name: str | None = None
    status: str = "active"

    @field_validator("student_code", "full_name")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("Khong duoc de trong.")
        return value

    @field_validator("class_name")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        value = (value or "").strip()
        return value or None

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        value = (value or "active").strip().lower()
        if value not in {"active", "inactive"}:
            raise ValueError("Trang thai chi duoc la active hoac inactive.")
        return value


class StudentUpdate(StudentCreate):
    pass


class FaceAnalyzeRequest(BaseModel):
    image: str


class StudentWorkTimeUpdate(BaseModel):
    work_start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    work_end_time: str = Field(pattern=r"^\d{2}:\d{2}$")

    @field_validator("work_start_time", "work_end_time")
    @classmethod
    def validate_time_range(cls, value: str) -> str:
        return validate_time_text(value)

from pydantic import BaseModel, Field, field_validator


class FaceRegistrationRequestReject(BaseModel):
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        value = (value or "").strip()
        if len(value) < 3:
            raise ValueError("Can nhap ly do tu choi.")
        return value

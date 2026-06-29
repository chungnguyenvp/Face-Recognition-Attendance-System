from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    role: str = Field(pattern="^(admin|lab_manager|student)$")
    student_id: int | None = None


class UserUpdate(BaseModel):
    password: str | None = Field(default=None, min_length=6, max_length=128)
    status: str | None = Field(default=None, pattern="^(active|inactive)$")
    student_id: int | None = None

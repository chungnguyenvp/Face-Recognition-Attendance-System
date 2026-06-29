from pydantic import BaseModel


class CameraStartPayload(BaseModel):
    source: str | None = None

from pydantic import BaseModel, ConfigDict


class CameraStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

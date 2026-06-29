from pydantic import BaseModel


class AlertStatusUpdate(BaseModel):
    status: str

from datetime import datetime

from pydantic import BaseModel, Field


class AlertOut(BaseModel):
    id: int
    service_name: str
    alert_type: str
    message: str
    created_at: datetime
    resolved: bool

    model_config = {"from_attributes": True}


class AlertResolveBody(BaseModel):
    resolved: bool = Field(default=True)

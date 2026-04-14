from datetime import datetime

from pydantic import BaseModel, Field


class MetricCreate(BaseModel):
    service_name: str = Field(..., max_length=128)
    endpoint: str = Field(..., max_length=256)
    latency_ms: float = Field(..., ge=0)
    status_code: int = Field(..., ge=100, le=599)
    timestamp: datetime | None = None


class MetricOut(BaseModel):
    id: int
    service_name: str
    endpoint: str
    latency_ms: float
    status_code: int
    timestamp: datetime

    model_config = {"from_attributes": True}


class MetricQuery(BaseModel):
    service_name: str | None = None
    endpoint: str | None = None
    from_ts: datetime | None = None
    to_ts: datetime | None = None
    limit: int = Field(default=500, le=5000)

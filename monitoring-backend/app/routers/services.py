import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_user
from app.database import get_db
from app.models import Metric, User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/services", tags=["services"])

KNOWN_SERVICES = ["monitored-service-1", "monitored-service-2"]


@router.get("")
async def list_services(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_user)],
):
    """Union of configured services and any service_name seen in metrics."""
    result = await db.execute(select(Metric.service_name).distinct())
    from_db = {r[0] for r in result.all()}
    names = sorted(set(KNOWN_SERVICES) | from_db)

    now = datetime.now(timezone.utc)
    stale_after = now - timedelta(seconds=90)

    out = []
    for name in names:
        last = await db.execute(
            select(Metric.timestamp, Metric.latency_ms, Metric.status_code)
            .where(Metric.service_name == name)
            .order_by(desc(Metric.timestamp))
            .limit(1)
        )
        row = last.first()
        if row is None:
            status = "down"
            last_ts = None
            last_latency = None
            last_code = None
        else:
            last_ts, last_latency, last_code = row[0], row[1], row[2]
            if last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=timezone.utc)
            if last_ts < stale_after:
                status = "down"
            elif last_code >= 500 or (last_latency and last_latency > 1500):
                status = "degraded"
            else:
                status = "healthy"

        out.append(
            {
                "service_name": name,
                "status": status,
                "last_metric_at": last_ts.isoformat() if last_ts else None,
                "last_latency_ms": last_latency,
                "last_status_code": last_code,
            }
        )
    return {"services": out}

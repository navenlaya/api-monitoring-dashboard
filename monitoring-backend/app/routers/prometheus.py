import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_user
from app.database import get_db
from app.models import Metric, User

logger = logging.getLogger(__name__)
router = APIRouter(tags=["prometheus"])


@router.get("/metrics/prometheus")
async def prometheus_metrics(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_user)],
    window_minutes: int = 15,
):
    """OpenMetrics-style text for dashboards or scraping (auth required here)."""
    since = func.now() - func.make_interval(0, 0, 0, 0, window_minutes)

    stmt = (
        select(
            Metric.service_name,
            func.count().label("request_count"),
            func.sum(case((Metric.status_code >= 400, 1), else_=0)).label("error_count"),
            func.avg(Metric.latency_ms).label("avg_latency"),
        )
        .where(Metric.timestamp >= since)
        .group_by(Metric.service_name)
    )
    result = await db.execute(stmt)
    rows = result.mappings().all()

    lines = [
        "# HELP monitoring_request_count Requests in window by service",
        "# TYPE monitoring_request_count counter",
        "# HELP monitoring_error_count Responses with status >= 400",
        "# TYPE monitoring_error_count counter",
        "# HELP monitoring_avg_latency_ms Average latency in window",
        "# TYPE monitoring_avg_latency_ms gauge",
    ]
    for r in rows:
        sn = r["service_name"].replace('"', '\\"')
        rc = int(r["request_count"] or 0)
        ec = int(r["error_count"] or 0)
        al = float(r["avg_latency"] or 0)
        lines.append(f'monitoring_request_count{{service_name="{sn}"}} {rc}')
        lines.append(f'monitoring_error_count{{service_name="{sn}"}} {ec}')
        lines.append(f'monitoring_avg_latency_ms{{service_name="{sn}"}} {al}')

    body = "\n".join(lines) + "\n"
    return Response(content=body, media_type="text/plain; charset=utf-8")

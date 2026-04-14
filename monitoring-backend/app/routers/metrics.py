import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin_or_ingest_token, require_user
from app.celery_app import celery_app
from app.database import get_db
from app.models import Metric, User
from app.schemas.metrics import MetricCreate, MetricOut
from app.services.redis_cache import cache_get_json, cache_set_json

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.post("", response_model=MetricOut, status_code=status.HTTP_201_CREATED)
async def ingest_metric(
    body: MetricCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User | None, Depends(require_admin_or_ingest_token)],
):
    ts = body.timestamp or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    row = Metric(
        service_name=body.service_name,
        endpoint=body.endpoint,
        latency_ms=body.latency_ms,
        status_code=body.status_code,
        timestamp=ts,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)

    try:
        celery_app.send_task(
            "app.tasks.evaluate_service_metrics",
            args=[body.service_name],
        )
    except Exception as e:
        logger.warning("enqueue evaluate_service_metrics failed: %s", e)

    return row


@router.get("", response_model=list[MetricOut])
async def list_metrics(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_user)],
    service_name: str | None = None,
    endpoint: str | None = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    limit: int = 500,
):
    if limit > 5000:
        raise HTTPException(status_code=400, detail="limit must be <= 5000")

    q = select(Metric).order_by(desc(Metric.timestamp)).limit(limit)
    conds = []
    if service_name:
        conds.append(Metric.service_name == service_name)
    if endpoint:
        conds.append(Metric.endpoint == endpoint)
    if from_ts:
        conds.append(Metric.timestamp >= from_ts)
    if to_ts:
        conds.append(Metric.timestamp <= to_ts)
    if conds:
        q = select(Metric).where(and_(*conds)).order_by(desc(Metric.timestamp)).limit(limit)

    result = await db.execute(q)
    return list(result.scalars().all())


@router.get("/summary")
async def metrics_summary(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_user)],
    window_minutes: int = 15,
):
    """Aggregated counts for dashboard (DB-backed; short Redis cache)."""
    cache_key = f"metrics:summary:{window_minutes}"
    cached = await cache_get_json(cache_key)
    if cached is not None:
        return cached

    since = func.now() - func.make_interval(0, 0, 0, 0, window_minutes)

    stmt = (
        select(
            Metric.service_name,
            func.count().label("request_count"),
            func.sum(case((Metric.status_code >= 400, 1), else_=0)).label("error_count"),
            func.avg(Metric.latency_ms).label("avg_latency_ms"),
        )
        .where(Metric.timestamp >= since)
        .group_by(Metric.service_name)
    )
    result = await db.execute(stmt)
    rows = result.mappings().all()
    out = {
        "window_minutes": window_minutes,
        "by_service": [
            {
                "service_name": r["service_name"],
                "request_count": int(r["request_count"] or 0),
                "error_count": int(r["error_count"] or 0),
                "avg_latency_ms": float(r["avg_latency_ms"] or 0),
            }
            for r in rows
        ],
    }
    await cache_set_json(cache_key, out, ttl_seconds=15)
    return out

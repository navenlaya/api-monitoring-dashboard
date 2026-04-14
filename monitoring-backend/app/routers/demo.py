import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import require_admin
from app.celery_app import celery_app
from app.models import User
from app.services.redis_cache import get_redis

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/demo", tags=["demo"])


class DemoTrafficRequest(BaseModel):
    seconds: int = Field(default=45, ge=5, le=120)
    rps: float = Field(default=8.0, ge=0.2, le=25.0)
    chaos_bias: float = Field(
        default=0.65,
        ge=0.0,
        le=1.0,
        description="Probability of sending requests to svc2 (chaos) vs svc1.",
    )


class DemoTrafficResponse(BaseModel):
    job_id: str
    seconds: int
    rps: float
    chaos_bias: float


async def _rate_limit_or_429(user: User) -> None:
    """
    Prevent spam. Limits per-user and globally using Redis counters.
    Also enforces a single active traffic job at a time (simple lock).
    """
    r = await get_redis()

    # One active job at a time (lock expires even if worker dies).
    lock_key = "demo:traffic:lock"
    locked = await r.set(lock_key, "1", ex=120, nx=True)
    if not locked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demo traffic already running. Try again shortly.",
        )

    # Per-user: max 2 starts / 5 minutes
    user_key = f"demo:traffic:user:{user.username}"
    user_count = await r.incr(user_key)
    if user_count == 1:
        await r.expire(user_key, 300)
    if user_count > 2:
        await r.delete(lock_key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limited (max 2 demo starts per 5 minutes).",
        )

    # Global: max 6 starts / 5 minutes
    global_key = "demo:traffic:global"
    global_count = await r.incr(global_key)
    if global_count == 1:
        await r.expire(global_key, 300)
    if global_count > 6:
        await r.delete(lock_key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limited (global demo limit exceeded).",
        )


@router.post("/traffic/start", response_model=DemoTrafficResponse)
async def start_demo_traffic(
    body: DemoTrafficRequest,
    user: Annotated[User, Depends(require_admin)],
):
    await _rate_limit_or_429(user)

    job_id = str(uuid.uuid4())
    try:
        celery_app.send_task(
            "app.demo_tasks.generate_demo_traffic",
            args=[job_id, body.seconds, body.rps, body.chaos_bias],
        )
        logger.info(
            "demo traffic started by %s job_id=%s seconds=%s rps=%s chaos_bias=%s",
            user.username,
            job_id,
            body.seconds,
            body.rps,
            body.chaos_bias,
        )
    except Exception as e:
        # Release lock if we failed to enqueue.
        r = await get_redis()
        await r.delete("demo:traffic:lock")
        raise HTTPException(status_code=500, detail=f"Failed to start demo traffic: {e}") from e

    return DemoTrafficResponse(
        job_id=job_id,
        seconds=body.seconds,
        rps=body.rps,
        chaos_bias=body.chaos_bias,
    )


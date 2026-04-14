import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.redis_cache import get_redis

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    db_ok = False
    redis_ok = False
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        logger.exception("db health: %s", e)
    try:
        r = await get_redis()
        await r.ping()
        redis_ok = True
    except Exception as e:
        logger.exception("redis health: %s", e)

    status = "ok" if db_ok and redis_ok else "degraded"
    return {
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dependencies": {"postgres": db_ok, "redis": redis_ok},
    }

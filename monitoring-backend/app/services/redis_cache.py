import json
import logging
from typing import Any

import redis.asyncio as redis

from app.config import get_settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


async def cache_get_json(key: str) -> Any | None:
    try:
        r = await get_redis()
        raw = await r.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.warning("redis get failed: %s", e)
        return None


async def cache_set_json(key: str, value: Any, ttl_seconds: int = 30) -> None:
    try:
        r = await get_redis()
        await r.set(key, json.dumps(value), ex=ttl_seconds)
    except Exception as e:
        logger.warning("redis set failed: %s", e)

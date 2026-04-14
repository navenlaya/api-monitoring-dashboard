import logging
import os
import random
import time

import httpx
import redis

from app.celery_app import celery_app
from app.config import get_settings

logger = logging.getLogger(__name__)


def _redis_sync() -> redis.Redis:
    return redis.from_url(get_settings().redis_url, decode_responses=True)


@celery_app.task(name="app.demo_tasks.generate_demo_traffic")
def generate_demo_traffic(job_id: str, seconds: int, rps: float, chaos_bias: float) -> None:
    """
    Generates demo traffic by calling services through Nginx on the internal Docker network.
    Uses a Redis lock set by the API endpoint; this task clears the lock at the end.
    """
    base = os.getenv("NGINX_BASE_URL", "http://nginx:8080").rstrip("/")
    svc1 = f"{base}/svc1"
    svc2 = f"{base}/svc2"
    paths = ["/users", "/orders"]

    stop_at = time.monotonic() + max(1, seconds)
    interval = 1.0 / max(0.1, float(rps))

    r = _redis_sync()
    try:
        with httpx.Client(timeout=10.0) as client:
            n = 0
            while time.monotonic() < stop_at:
                svc = svc2 if random.random() < float(chaos_bias) else svc1
                path = random.choice(paths)
                url = f"{svc}{path}"
                try:
                    client.get(url)
                except Exception:
                    pass
                n += 1
                time.sleep(interval)
        logger.info("demo traffic done job_id=%s sent=%s", job_id, n)
    finally:
        # Clear the lock so the button can be used again.
        try:
            r.delete("demo:traffic:lock")
        except Exception:
            pass


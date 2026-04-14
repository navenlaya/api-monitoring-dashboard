import asyncio
import logging
import os
import random
import time
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, HTTPException, Request

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SERVICE_NAME = os.getenv("SERVICE_NAME", "monitored-service-1")
MONITORING_URL = os.getenv("MONITORING_URL", "http://localhost:8000").rstrip("/")
INGEST_TOKEN = os.getenv("METRICS_INGEST_TOKEN", "dev-internal-metrics-token")
CHAOS_MODE = os.getenv("CHAOS_MODE", "false").lower() in ("1", "true", "yes")

app = FastAPI(title=f"Fake API — {SERVICE_NAME}")


async def _push_metric(endpoint: str, latency_ms: float, status_code: int) -> None:
    payload = {
        "service_name": SERVICE_NAME,
        "endpoint": endpoint,
        "latency_ms": latency_ms,
        "status_code": status_code,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    url = f"{MONITORING_URL}/metrics"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(
                url,
                json=payload,
                headers={"X-Internal-Token": INGEST_TOKEN},
            )
            if r.status_code >= 400:
                logger.warning("metrics push failed: %s %s", r.status_code, r.text)
    except Exception as e:
        logger.warning("metrics push error: %s", e)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception:
        status_code = 500
        raise
    finally:
        latency_ms = (time.perf_counter() - start) * 1000.0
        path = request.url.path
        asyncio.create_task(_push_metric(path, latency_ms, status_code))


@app.get("/users")
async def users():
    if CHAOS_MODE and random.random() < 0.12:
        await asyncio.sleep(random.uniform(0.8, 3.5))
    if CHAOS_MODE and random.random() < 0.08:
        raise HTTPException(status_code=random.choice([500, 502, 503]), detail="chaos")
    return {"service": SERVICE_NAME, "users": [{"id": 1, "name": "Ada"}, {"id": 2, "name": "Bob"}]}


@app.get("/orders")
async def orders():
    if CHAOS_MODE and random.random() < 0.1:
        await asyncio.sleep(random.uniform(0.5, 4.0))
    if CHAOS_MODE and random.random() < 0.07:
        raise HTTPException(status_code=random.choice([500, 429]), detail="chaos")
    return {"service": SERVICE_NAME, "orders": [{"id": 10, "total": 42.5}]}


@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME}

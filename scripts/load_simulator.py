#!/usr/bin/env python3
"""
Simulates traffic against monitored fake services: steady load, spikes, and bursts.

Usage (PEP 668–safe: use a venv, not system pip):
  python3 -m venv .venv && .venv/bin/pip install -r scripts/requirements-load.txt
  .venv/bin/python scripts/load_simulator.py --base http://localhost:8080
"""
from __future__ import annotations

import argparse
import asyncio
import random
import time
from dataclasses import dataclass

import httpx


@dataclass
class Phase:
    name: str
    duration_s: float
    rps: float
    paths: list[str]


async def worker(
    client: httpx.AsyncClient,
    base: str,
    paths: list[str],
    stop_at: float,
    per_worker_rps: float,
):
    services = [f"{base}/svc1", f"{base}/svc2"]
    while time.monotonic() < stop_at:
        svc = random.choice(services)
        path = random.choice(paths)
        url = f"{svc}{path}"
        try:
            await client.get(url, timeout=10.0)
        except Exception:
            pass
        if per_worker_rps > 0:
            await asyncio.sleep(random.expovariate(per_worker_rps))


async def run_phase(client: httpx.AsyncClient, base: str, phase: Phase) -> None:
    stop_at = time.monotonic() + phase.duration_s
    workers = max(1, min(40, int(phase.rps)))
    per_worker = phase.rps / workers
    tasks = [
        asyncio.create_task(worker(client, base, phase.paths, stop_at, per_worker))
        for _ in range(workers)
    ]
    await asyncio.gather(*tasks)


async def amain():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8080", help="Nginx base URL")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    phases = [
        Phase("normal", duration_s=30, rps=5, paths=["/users", "/orders"]),
        Phase("spike", duration_s=15, rps=40, paths=["/users", "/orders"]),
        Phase("failure_burst", duration_s=12, rps=25, paths=["/users", "/orders"]),
        Phase("cooldown", duration_s=20, rps=4, paths=["/users", "/orders"]),
    ]

    async with httpx.AsyncClient() as client:
        for p in phases:
            workers = max(1, min(40, int(p.rps)))
            print(f"phase={p.name} duration={p.duration_s}s workers={workers} target_rps~{p.rps}")
            await run_phase(client, base, p)


if __name__ == "__main__":
    asyncio.run(amain())

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.auth.jwt_utils import hash_password
from app.config import get_settings
from app.database import AsyncSessionLocal, Base, engine
from app.models import User
from app.routers import alerts, auth, demo, health, metrics, prometheus, services

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        for username, password, role in (
            ("admin", settings.default_admin_password, "admin"),
            ("viewer", settings.default_viewer_password, "viewer"),
        ):
            existing = await session.execute(select(User).where(User.username == username))
            if existing.scalar_one_or_none() is None:
                session.add(
                    User(
                        username=username,
                        hashed_password=hash_password(password),
                        role=role,
                    )
                )
                logger.info("seeded user: %s (%s)", username, role)
        await session.commit()

    yield
    await engine.dispose()


app = FastAPI(title="API Monitoring Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(metrics.router)
app.include_router(services.router)
app.include_router(alerts.router)
app.include_router(prometheus.router)
app.include_router(demo.router)

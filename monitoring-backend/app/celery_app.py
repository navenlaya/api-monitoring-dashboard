import logging

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

celery_app = Celery(
    "monitoring",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks", "app.demo_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "evaluate-all-services": {
            "task": "app.tasks.evaluate_all_services",
            "schedule": crontab(minute="*"),
        },
        "check-stale-services": {
            "task": "app.tasks.check_stale_services",
            "schedule": crontab(minute="*"),
        },
    },
)

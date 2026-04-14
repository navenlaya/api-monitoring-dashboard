import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.celery_app import celery_app
from app.config import get_settings
from app.models import Alert, Metric

logger = logging.getLogger(__name__)

_sync_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def _session() -> Session:
    global _sync_engine, _SessionLocal
    if _sync_engine is None:
        settings = get_settings()
        _sync_engine = create_engine(settings.database_url_sync, pool_pre_ping=True)
        _SessionLocal = sessionmaker(bind=_sync_engine, autoflush=False, autocommit=False)
    assert _SessionLocal is not None
    return _SessionLocal()


def _recent_open_alert(
    session: Session, service_name: str, alert_type: str, within_seconds: int | None
) -> bool:
    """
    Returns True if there is already an open (unresolved) alert matching service+type.

    For most alert types we dedupe within a short window to avoid spamming identical rows.
    For service_down we dedupe for as long as the incident remains open.
    """
    conds = [
        Alert.service_name == service_name,
        Alert.alert_type == alert_type,
        Alert.resolved.is_(False),
    ]
    if within_seconds is not None:
        since = datetime.now(timezone.utc) - timedelta(seconds=within_seconds)
        conds.append(Alert.created_at >= since)

    q = select(Alert.id).where(and_(*conds)).limit(1)
    return session.execute(q).scalar_one_or_none() is not None


def _insert_alert(session: Session, service_name: str, alert_type: str, message: str) -> None:
    # service_down should not create a new open row every minute while still unresolved
    if alert_type == "service_down":
        if _recent_open_alert(session, service_name, alert_type, within_seconds=None):
            return
    else:
        if _recent_open_alert(session, service_name, alert_type, within_seconds=300):
            return
    session.add(
        Alert(
            service_name=service_name,
            alert_type=alert_type,
            message=message,
            resolved=False,
        )
    )
    session.commit()
    logger.info("alert created: %s %s", service_name, alert_type)


@celery_app.task(name="app.tasks.evaluate_service_metrics")
def evaluate_service_metrics(service_name: str) -> None:
    settings = get_settings()
    session = _session()
    try:
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(seconds=settings.alert_error_window_seconds)

        q = select(Metric).where(
            and_(Metric.service_name == service_name, Metric.timestamp >= window_start)
        )
        rows = list(session.scalars(q).all())
        if len(rows) < settings.alert_min_samples:
            return

        errors = sum(1 for m in rows if m.status_code >= 400)
        err_rate = (errors / len(rows)) * 100.0
        avg_lat = sum(m.latency_ms for m in rows) / len(rows)

        if err_rate > settings.alert_error_rate_percent:
            _insert_alert(
                session,
                service_name,
                "error_rate",
                f"Error rate {err_rate:.1f}% over last {settings.alert_error_window_seconds}s "
                f"(threshold {settings.alert_error_rate_percent}%, n={len(rows)})",
            )

        if avg_lat > settings.alert_latency_ms:
            _insert_alert(
                session,
                service_name,
                "latency",
                f"Avg latency {avg_lat:.0f}ms over last {settings.alert_error_window_seconds}s "
                f"(threshold {settings.alert_latency_ms}ms, n={len(rows)})",
            )
    except Exception:
        logger.exception("evaluate_service_metrics failed for %s", service_name)
        session.rollback()
    finally:
        session.close()


@celery_app.task(name="app.tasks.evaluate_all_services")
def evaluate_all_services() -> None:
    session = _session()
    try:
        names = list(session.execute(select(Metric.service_name).distinct()).scalars().all())
        for name in names:
            evaluate_service_metrics.delay(name)
    finally:
        session.close()


@celery_app.task(name="app.tasks.check_stale_services")
def check_stale_services() -> None:
    settings = get_settings()
    session = _session()
    try:
        now = datetime.now(timezone.utc)
        stale_before = now - timedelta(seconds=settings.alert_stale_seconds)
        known = ["monitored-service-1", "monitored-service-2"]
        for name in known:
            last_ts = session.execute(
                select(func.max(Metric.timestamp)).where(Metric.service_name == name)
            ).scalar_one_or_none()
            if last_ts is not None and last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=timezone.utc)
            if last_ts is None or last_ts < stale_before:
                _insert_alert(
                    session,
                    name,
                    "service_down",
                    "No recent metrics received (service may be down or not reporting)",
                )
    except Exception:
        logger.exception("check_stale_services failed")
        session.rollback()
    finally:
        session.close()

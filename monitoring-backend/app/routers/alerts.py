import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin, require_user
from app.database import get_db
from app.models import Alert, User
from app.schemas.alerts import AlertOut, AlertResolveBody

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertOut])
async def list_alerts(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_user)],
    resolved: bool | None = None,
    service_name: str | None = None,
    limit: int = 200,
):
    lim = min(limit, 1000)
    conds = []
    if resolved is not None:
        conds.append(Alert.resolved == resolved)
    if service_name:
        conds.append(Alert.service_name == service_name)

    q = select(Alert).order_by(desc(Alert.created_at)).limit(lim)
    if conds:
        q = select(Alert).where(and_(*conds)).order_by(desc(Alert.created_at)).limit(lim)

    result = await db.execute(q)
    return list(result.scalars().all())


@router.patch("/{alert_id}/resolve", response_model=AlertOut)
async def resolve_alert(
    alert_id: int,
    body: AlertResolveBody,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_admin)],
):
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    alert.resolved = body.resolved
    await db.flush()
    await db.refresh(alert)
    return alert

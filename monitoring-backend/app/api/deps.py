import logging
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt_utils import decode_token
from app.database import get_db
from app.models import User

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)


async def get_current_user_optional(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if credentials is None:
        return None
    try:
        payload = decode_token(credentials.credentials)
        username = payload.get("sub")
        if not username:
            return None
    except ValueError:
        return None

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    return user


async def require_user(
    user: Annotated[User | None, Depends(get_current_user_optional)],
):
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


async def require_admin(user: Annotated[User, Depends(require_user)]):
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return user


def metrics_ingest_token_valid(x_internal_token: str | None) -> bool:
    from app.config import get_settings

    if not x_internal_token:
        return False
    return x_internal_token == get_settings().metrics_ingest_token


async def require_admin_or_ingest_token(
    user: Annotated[User | None, Depends(get_current_user_optional)],
    x_internal_token: Annotated[str | None, Header(alias="X-Internal-Token")] = None,
):
    """Allow metric ingestion from trusted services (header) or admin JWT."""
    if metrics_ingest_token_valid(x_internal_token):
        return None
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin or ingest token required")
    return user

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from app.infra.database import AsyncSessionFactory

from .exceptions import UnauthorizedError
from .models import User
from .security import user_id_from_token


_bearer = HTTPBearer(auto_error=False)


async def get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> int:
    if credentials is None:
        raise UnauthorizedError()

    user_id = user_id_from_token(credentials.credentials)
    # 此查询有自己的短会话，业务 Service 可独立开启写事务。
    async with AsyncSessionFactory() as session:
        active_user_id = await session.scalar(
            select(User.id).where(User.id == user_id, User.status == "active")
        )
    if active_user_id is None:
        raise UnauthorizedError()
    return active_user_id

from sqlalchemy import or_, select
from starlette.concurrency import run_in_threadpool

from app.infra.database import AsyncSessionFactory

from .exceptions import InvalidCredentialsError
from .models import User
from .schemas import LoginRequest, LoginResponse, UserSummary
from .security import create_access_token, verify_password


async def login_user(request: LoginRequest) -> LoginResponse:
    login = request.username.strip()
    password = request.password.get_secret_value()
    if not login or not password.strip():
        raise InvalidCredentialsError()

    async with AsyncSessionFactory() as session:
        users = (
            await session.scalars(
                select(User).where(or_(User.username == login, User.email == login)).limit(2)
            )
        ).all()
        user = users[0] if len(users) == 1 and users[0].status == "active" else None

    password_hash = user.password_hash if user is not None else None
    if not await run_in_threadpool(verify_password, password, password_hash) or user is None:
        raise InvalidCredentialsError()

    return LoginResponse(
        access_token=create_access_token(user.id),
        user=UserSummary(
            id=user.id,
            username=user.username,
            email=user.email,
            display_name=user.display_name,
        ),
    )

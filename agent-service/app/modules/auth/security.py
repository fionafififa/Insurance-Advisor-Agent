from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from app.core.config import settings

from .exceptions import UnauthorizedError


_ALGORITHM = "HS256"
_ISSUER = "insurance-agent-service"
_AUDIENCE = "insurance-agent-api"
_MAX_USER_ID = (1 << 63) - 1

_password_hasher = PasswordHash.recommended()
_dummy_password_hash = _password_hasher.hash(token_urlsafe(48))


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if password_hash is not None:
        try:
            return _password_hasher.verify(password, password_hash)
        except UnknownHashError:
            # 初始化 SQL 中的示例占位值需要由管理者设置密码后才能登录。
            pass
    _password_hasher.verify(password, _dummy_password_hash)
    return False


def create_access_token(user_id: int) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(minutes=settings.auth.access_token_ttl_minutes),
            "iss": _ISSUER,
            "aud": _AUDIENCE,
        },
        settings.auth.jwt_secret.get_secret_value(),
        algorithm=_ALGORITHM,
    )


def user_id_from_token(token: str) -> int:
    try:
        claims = jwt.decode(
            token,
            settings.auth.jwt_secret.get_secret_value(),
            algorithms=[_ALGORITHM],
            issuer=_ISSUER,
            audience=_AUDIENCE,
            options={"require": ["sub", "iat", "exp", "iss", "aud"]},
        )
        subject = claims["sub"]
        if not isinstance(subject, str) or len(subject) > 19 or not (
            subject.isascii() and subject.isdecimal()
        ):
            raise UnauthorizedError()
        user_id = int(subject)
        if user_id < 1 or user_id > _MAX_USER_ID:
            raise UnauthorizedError()
        return user_id
    except (jwt.InvalidTokenError, TypeError, ValueError, OverflowError):
        raise UnauthorizedError() from None

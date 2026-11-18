from fastapi import APIRouter, Response

from .schemas import LoginRequest, LoginResponse
from .service import login_user


router = APIRouter(prefix="/api/v1/auth", tags=["用户认证"])


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, response: Response) -> LoginResponse:
    result = await login_user(request)
    response.headers["Cache-Control"] = "no-store"
    return result

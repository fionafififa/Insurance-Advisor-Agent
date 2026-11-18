from typing import Literal

from pydantic import BaseModel, Field, SecretStr


class LoginRequest(BaseModel):
    username: str = Field(max_length=160)
    password: SecretStr = Field(max_length=1024)


class UserSummary(BaseModel):
    id: int
    username: str
    email: str
    display_name: str | None


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    user: UserSummary

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.database import get_session
from app.modules.auth.dependencies import get_current_user_id
from app.modules.chat_thread.repository import ChatThreadRepository
from .schema import ChatRequest
from .service import ChatService

router = APIRouter(prefix="/api/v1/chat", tags=["与AI对话接口"])


async def get_authorized_stream(
    body: ChatRequest,
    request: Request,
    user_id: Annotated[int, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session, scope="function")],
) -> AsyncIterator[ServerSentEvent]:
    # FastAPI 在发送 SSE 响应头之前执行依赖，此时仍能返回普通的 401 或 404。
    await ChatThreadRepository(session).require_owned(user_id, body.thread_id)
    return ChatService(request.app.state.agent).chat_stream(body)


@router.post("", response_class=EventSourceResponse)
async def chat(
    stream: Annotated[AsyncIterator[ServerSentEvent], Depends(get_authorized_stream)],
) -> AsyncIterator[ServerSentEvent]:
    async for event in stream:
        yield event


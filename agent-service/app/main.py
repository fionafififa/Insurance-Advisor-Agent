from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.exceptions import ApplicationError
from app.core.logging import configure_logging, get_logger
from app.modules.auth.exceptions import InvalidCredentialsError
from app.modules.auth.router import login, router as auth_router
import uvicorn

# 初始化日志系统
configure_logging(settings.logging.level)

logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"【{settings.app.name}】应用启动中...")
    from app.agents.orchestrator import init_insurance_agent
    from app.infra.database import check_database, close_database
    from app.infra.checkpointer import init_checkpointer, close_checkpointer
    from app.rag import close_rag

    try:
        # 1.初始化数据库连接池
        await check_database()
        # 2.初始化Checkpointer
        checkpointer = await init_checkpointer()
        # 3.初始化Agent,并将其保存在FastAPI的全局State中，一切进入FastAPI的请求都共享这个State
        app.state.agent = await init_insurance_agent(checkpointer)
        yield
    finally:
        logger.info("应用关闭中... ")
        # 4.关闭rag
        close_rag()
        # 5.关闭数据库连接池
        await close_database()
        # 6.关闭Checkpointer连接池
        await close_checkpointer()


app = FastAPI(
    title=settings.app.name,
    debug=settings.app.debug,
    lifespan=lifespan
)

# CORS配置，解决跨域问题
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", summary="健康检测接口")
async def health_check() -> dict[str, str]:
    logger.info("执行健康检查")
    return {"status": "ok"}

@app.exception_handler(ApplicationError)
def handle_exception(request: Request, exc: ApplicationError):
    logger.info("业务请求失败", path=request.url.path, code=exc.code, status_code=exc.status_code)
    return JSONResponse(
        headers=exc.headers,
        status_code=exc.status_code,  # http状态码
        content={
            "code": exc.code,        # 错误码， error_code
            "message": exc.message     # 错误消息，error_message
        }
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    if request.scope.get("endpoint") is login:
        # 登录参数校验失败时，默认错误详情可能包含客户端提交的明文密码。
        return handle_exception(request, InvalidCredentialsError())
    return await request_validation_exception_handler(request, exc)


from app.modules.product.router import router as product_router
from app.modules.chat_thread.router import router as chat_thread_router
from app.modules.chat.router import router as chat_router
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(chat_thread_router)
app.include_router(product_router)

if __name__ == "__main__":
    import sys
    uvicorn.run(
        "app.main:app",
        host=settings.app.host,
        port=settings.app.port,
        reload=False,
        loop= "asyncio:SelectorEventLoop" if sys.platform == "win32" else "auto",
    )

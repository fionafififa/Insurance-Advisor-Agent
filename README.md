# 安心保智能保险顾问

- `agent-service/` 是 FastAPI 后端，包含会话管理、Agent 工作流和条款检索。
- `frontend/` 是 React 前端。
- `deploy/` 包含本地依赖服务和 PostgreSQL 初始化脚本。

运行前端的说明见 [frontend/README.md](frontend/README.md)。后端的环境变量定义在 [app/core/config.py](agent-service/app/core/config.py)，实际值放在本地的 `agent-service/.env`。

启动 Docker Compose 前，把 `deploy/milvus/user.example.yaml` 复制为 `deploy/milvus/user.yaml`，并在使用条款重排功能时填入自己的 DashScope API key。在本地的 `deploy/.env` 设置 `POSTGRES_PASSWORD`，并把相同的密码配置为后端的 `DB_PASSWORD`。

如需重建条款知识库，将条款 PDF 放到 `agent-service/data/raw/kb/`，再运行 `agent-service/scripts/ingest_rag.py`。

## 登录与会话

后端通过 PostgreSQL 的 `users` 表验证用户名或邮箱和密码。登录成功后，浏览器在当前标签页保存访问令牌，刷新页面可继续对话。令牌默认 30 分钟有效，可通过 `AUTH_ACCESS_TOKEN_TTL_MINUTES` 调整。

1. 在 `agent-service` 目录执行 `uv sync --locked`。新环境首次配置时，在同一目录执行下列命令，为本地 `.env` 追加随机签名密钥。已有 `AUTH_JWT_SECRET` 的环境沿用原值。同一部署的后端实例使用相同密钥。

   ```powershell
   uv run python -c "import secrets; print('\nAUTH_JWT_SECRET=' + secrets.token_urlsafe(48))" | Add-Content -Encoding utf8 .env
   ```

2. 启动并初始化 PostgreSQL 后，在 `agent-service` 目录创建一个登录账号。按终端提示输入两次密码，长度为 6 至 1024 个字符。

   ```powershell
   uv run python -m scripts.provision_user --username student --email student@example.com
   ```

   若要沿用初始化脚本中的演示用户及其会话，可执行 `uv run python -m scripts.provision_user --username demo --reset-password` 为它设置密码。

3. 确认项目依赖服务已启动，在 `agent-service` 目录执行 `uv run python -m app.main`。启动前端后，在商城点“登录”，再进入智能顾问。会话列表、发送消息、历史、改名和删除都使用登录账号的身份。

回归测试位于 [test_session_authorization.py](agent-service/tests/test_session_authorization.py)。将 `TEST_POSTGRES_DSN` 设置为有创建 schema 权限的 PostgreSQL **测试库**连接串后，在 `agent-service` 目录执行 `uv run python -m unittest discover -s tests -v`。每个测试建立并清理独立 schema。

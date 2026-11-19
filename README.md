# 安心保智能保险顾问

- `agent-service/` 是 FastAPI 后端，包含会话管理、Agent 工作流和条款检索。
- `frontend/` 是 React 前端。
- `deploy/` 包含本地依赖服务和 PostgreSQL 初始化脚本。

运行前端的说明见 [frontend/README.md](frontend/README.md)。后端的环境变量定义在 [app/core/config.py](agent-service/app/core/config.py)，实际值放在本地的 `agent-service/.env`。

启动 Docker Compose 前，把 `deploy/milvus/user.example.yaml` 复制为 `deploy/milvus/user.yaml`，并在使用条款重排功能时填入自己的 DashScope API key。在本地的 `deploy/.env` 设置 `POSTGRES_PASSWORD`，并把相同的密码配置为后端的 `DB_PASSWORD`。

如需重建条款知识库，将条款 PDF 放到 `agent-service/data/raw/kb/`，再运行 `agent-service/scripts/ingest_rag.py`。

## 相对初始源码的完善

以下以本仓库首次导入的源码提交 `6313d12` 为对照，方便学习和参考。

| 部分 | 初始源码 | 当前实现 |
| --- | --- | --- |
| 用户登录 | 前端使用固定的模拟登录信息 | 新增登录接口，使用 PostgreSQL 用户表和 Argon2 密码哈希验证用户名或邮箱及密码，成功后签发限时 JWT |
| 用户身份 | 会话和聊天接口从请求头 `x-user-id` 接收用户 ID | 前端发送 `Authorization: Bearer <access_token>`，后端校验令牌及账号状态后取得用户 ID |
| 会话授权 | 业务代码检查会话归属，聊天接口在 SSE 生成过程中检查 | 会话的发送消息、历史查询、改名和删除统一检查归属。不存在和不属于当前用户的会话返回相同的 `404`，聊天接口在 SSE 响应开始前完成校验 |
| 前端会话 | 使用模拟账号 | 登录表单连接后端，令牌保存在当前标签页的 `sessionStorage` 中，过期或无效时清除登录状态 |
| 本地账号 | 初始化脚本中的演示账号密码为占位值 | 增加命令行脚本创建账号或为已有账号设置密码 |
| 数据库配置 | 数据库连接地址未使用配置的 `DB_NAME` | 业务数据库连接和检查点数据库连接均使用 `DB_NAME` |
| 验证 | 没有此项会话授权的自动化回归测试 | 增加登录、双账号会话隔离、失效凭证、SSE 和会话操作的集成测试 |

当前账号通过本地命令行脚本管理。令牌默认有效期为 30 分钟，浏览器遇到 `401` 时需要重新登录。

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

# 安心保智能保险顾问

- `agent-service/` 是 FastAPI 后端，包含会话管理、Agent 工作流和条款检索。
- `frontend/` 是 React 前端。
- `deploy/` 包含本地依赖服务和 PostgreSQL 初始化脚本。

运行前端的说明见 [frontend/README.md](frontend/README.md)。后端的环境变量定义在 [app/core/config.py](agent-service/app/core/config.py)，实际值放在本地的 `agent-service/.env`。

启动 Docker Compose 前，把 `deploy/milvus/user.example.yaml` 复制为 `deploy/milvus/user.yaml`，并在使用条款重排功能时填入自己的 DashScope API key。在本地的 `deploy/.env` 设置 `POSTGRES_PASSWORD`，并把相同的密码配置为后端的 `DB_PASSWORD`。

如需重建条款知识库，将条款 PDF 放到 `agent-service/data/raw/kb/`，再运行 `agent-service/scripts/ingest_rag.py`。

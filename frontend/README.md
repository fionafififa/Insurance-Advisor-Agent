# frontend

React + Ant Design 保险商城和智能客服前端。

## 本地运行

在 `frontend` 目录执行以下命令。

```powershell
npm ci
npm run dev
```

访问：

```text
http://localhost:5173
```

公开产品可直接浏览。使用智能顾问时，在商城登录窗口输入已创建的用户名或邮箱和密码。后端账号配置见[项目说明](../README.md#登录与会话)。

## 后端地址配置

本地开发默认代理到 `http://127.0.0.1:8001`。如需覆盖，复制 `.env.example` 为 `.env.local` 后修改 `VITE_BACKEND_HOST` 和 `VITE_BACKEND_PORT`。

容器运行时通过 `BACKEND_HOST` 和 `BACKEND_PORT` 配置 Nginx 代理目标，默认值为 `backend:8001`。

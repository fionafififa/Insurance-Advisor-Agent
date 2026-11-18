"""Run with TEST_POSTGRES_DSN pointing to a PostgreSQL test DB with CREATE privilege.

From agent-service: python -m unittest discover -s tests -v
Each test uses its own schema, users, signing key, and in-memory graph checkpoints.
"""

import json
import os
import secrets
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import httpx
import jwt
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from pydantic import SecretStr
from sqlalchemy import select, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema


LOGIN = "/api/v1/auth/login"
THREADS = "/api/v1/chat-threads"
CHAT = "/api/v1/chat"


def thread_requests(thread_id):
    return [
        ("POST", CHAT, {"thread_id": thread_id, "message": "你好"}),
        ("GET", f"{THREADS}/{thread_id}/messages", None),
        ("PATCH", f"{THREADS}/{thread_id}", {"title": "新标题"}),
        ("DELETE", f"{THREADS}/{thread_id}", None),
    ]


@unittest.skipUnless(os.getenv("TEST_POSTGRES_DSN"), "set TEST_POSTGRES_DSN to a test database")
class SessionAuthorizationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Allow a clean checkout to run without model keys or the developer's .env.
        test_key = secrets.token_urlsafe(48)
        self.enterContext(patch.dict(os.environ, {
            "APP_NAME": "auth-test", "DB_PASSWORD": "unused", "AUTH_JWT_SECRET": test_key,
            "DEEPSEEK_API_KEY": "unused", "DASHSCOPE_API_KEY": "unused",
            "DASHSCOPE_BASE_URL": "https://example.invalid", "MINERU_TOKEN": "unused",
        }))
        from app.core.config import settings
        from app.infra import database
        from app.main import app
        from app.modules.auth import dependencies, service
        from app.modules.auth.models import User
        from app.modules.auth.security import hash_password
        from app.modules.chat_thread.models import ChatThread

        self.enterContext(patch.object(settings.auth, "jwt_secret", SecretStr(test_key)))
        self.key = test_key
        schema = "auth_test_" + uuid4().hex
        url = make_url(os.environ["TEST_POSTGRES_DSN"]).set(drivername="postgresql+asyncpg")
        engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
        self.addAsyncCleanup(engine.dispose)
        async with engine.begin() as conn:
            await conn.execute(CreateSchema(schema))
            for table in (User.__table__, ChatThread.__table__):
                await conn.run_sync(table.create)

        async def drop_test_schema():
            async with engine.begin() as conn:
                await conn.execute(DropSchema(schema, cascade=True))
        self.addAsyncCleanup(drop_test_schema)

        self.sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        for module in (database, dependencies, service):
            self.enterContext(patch.object(module, "AsyncSessionFactory", self.sessions))
        self.password = secrets.token_urlsafe(24)
        password_hash = hash_password(self.password)
        async with self.sessions.begin() as session:
            session.add_all([
                User(id=uid, username=name, email=f"{name}@example.org",
                     display_name=name.title(), password_hash=password_hash)
                for uid, name in [(1, "alice"), (2, "bob")]
            ])

        graph = StateGraph(MessagesState)
        graph.add_node("reply", lambda state: {
            "messages": [AIMessage("回声：" + state["messages"][-1].text)]
        })
        graph.add_edge(START, "reply")
        graph.add_edge("reply", END)
        saver = InMemorySaver()
        agent = graph.compile(checkpointer=saver)
        self.agent = Mock(wraps=agent)
        self.agent.aget_state = AsyncMock(wraps=agent.aget_state)
        self.agent.checkpointer.adelete_thread = AsyncMock(wraps=saver.adelete_thread)
        self.enterContext(patch.object(app.state, "agent", self.agent, create=True))
        self.client = await self.enterAsyncContext(httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ))

    async def login(self, name):
        res = await self.client.post(LOGIN, json={"username": name, "password": self.password})
        self.assertEqual(res.status_code, 200, res.text)
        return {"Authorization": "Bearer " + res.json()["access_token"]}

    async def create_thread(self, headers):
        res = await self.client.post(THREADS, headers=headers, json={"title": "原始会话"})
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()["id"]

    async def snapshot(self):
        from app.modules.chat_thread.models import ChatThread

        async with self.sessions() as session:
            return (await session.execute(select(ChatThread.__table__).order_by(ChatThread.id))).all()

    async def test_password_login_and_disabled_account(self):
        from app.modules.auth.models import User

        email = "alice@example.org"
        for identifier in ("alice", email):
            res = await self.client.post(LOGIN, json={"username": identifier, "password": self.password})
            self.assertEqual(res.status_code, 200, res.text)
            self.assertEqual(res.json()["token_type"], "Bearer")
            self.assertEqual(res.json()["user"], {
                "id": 1, "username": "alice", "email": email, "display_name": "Alice",
            })
        headers = await self.login(email)
        async with self.sessions.begin() as session:
            await session.execute(update(User).where(User.id == 1).values(status="disabled"))
        for name, password in [("alice", self.password), ("bob", "wrong"), ("nobody", self.password),
                               ("", self.password), ("bob", "")]:
            with self.subTest(name=name):
                res = await self.client.post(LOGIN, json={"username": name, "password": password})
                self.assertEqual(res.status_code, 400, res.text)
                self.assertEqual(res.json()["code"], "INVALID_CREDENTIALS")
        for body in ({"password": self.password}, {"username": "bob", "password": [self.password]}):
            res = await self.client.post(LOGIN, json=body)
            self.assertEqual(res.status_code, 400)
            self.assertEqual(res.json()["code"], "INVALID_CREDENTIALS")
            self.assertNotIn(self.password, res.text)
        self.assertEqual((await self.client.get(THREADS, headers=headers)).status_code, 401)

    async def test_owned_thread_lifecycle_and_continuation(self):
        headers = await self.login("alice")
        thread_id = await self.create_thread(headers)
        for line in ("第一条", "第二条"):
            res = await self.client.post(CHAT, headers=headers, json={"thread_id": thread_id, "message": line})
            self.assertEqual(res.status_code, 200, res.text)
            self.assertTrue(res.headers["content-type"].startswith("text/event-stream"))
            self.assertIn("event: message", res.text)
            values = [json.loads(value[6:]) for value in res.text.splitlines() if value.startswith("data: ")]
            self.assertIn("回声：" + line, values)
            self.assertIn("event: done", res.text)
        res = await self.client.get(f"{THREADS}/{thread_id}/messages", headers=headers)
        self.assertEqual(res.json()["messages"], [
            {"role": "user", "content": "第一条"}, {"role": "assistant", "content": "回声：第一条"},
            {"role": "user", "content": "第二条"}, {"role": "assistant", "content": "回声：第二条"},
        ])
        self.assertEqual([t["id"] for t in (await self.client.get(THREADS, headers=headers)).json()], [thread_id])
        res = await self.client.patch(f"{THREADS}/{thread_id}", headers=headers, json={"title": "已改名"})
        self.assertEqual(res.json()["title"], "已改名")
        self.assertEqual((await self.client.delete(f"{THREADS}/{thread_id}", headers=headers)).status_code, 204)
        self.agent.checkpointer.adelete_thread.assert_awaited_once_with(thread_id)
        self.assertEqual(await self.snapshot(), [])

    async def test_foreign_and_absent_threads_are_indistinguishable(self):
        bob = await self.login("bob")
        thread_id = await self.create_thread(bob)
        alice = {**await self.login("alice"), "x-user-id": "2"}
        self.assertEqual((await self.client.get(THREADS, headers=alice)).json(), [])
        before = await self.snapshot()
        for foreign, absent in zip(thread_requests(thread_id), thread_requests(str(uuid4())), strict=True):
            with self.subTest(method=foreign[0], path=foreign[1]):
                results = []
                for method, path, body in (foreign, absent):
                    res = await self.client.request(method, path, headers=alice, json=body)
                    self.assertEqual(res.status_code, 404, res.text)
                    self.assertEqual(res.headers["content-type"], "application/json")
                    self.assertEqual(res.json()["code"], "CHAT_THREAD_NOT_FOUND")
                    results.append(res.json())
                self.assertEqual(*results)
        self.assertEqual(await self.snapshot(), before)
        self.agent.astream_events.assert_not_called()
        self.agent.aget_state.assert_not_called()
        self.agent.checkpointer.adelete_thread.assert_not_called()

    async def test_all_routes_reject_missing_invalid_and_expired_credentials(self):
        headers = await self.login("alice")
        thread_id = await self.create_thread(headers)
        token = headers["Authorization"].split()[1]
        claims = jwt.decode(token, options={"verify_signature": False})
        bad_signature = jwt.encode(claims, secrets.token_urlsafe(48), algorithm="HS256")
        past = datetime.now(UTC) - timedelta(hours=1)
        claims.update(iat=past, exp=past + timedelta(seconds=1))
        expired = jwt.encode(claims, self.key, algorithm="HS256")
        before = await self.snapshot()
        for credential in (None, "Bearer invalid", "Bearer " + bad_signature, "Bearer " + expired):
            headers = {"x-user-id": "1"}
            if credential:
                headers["Authorization"] = credential
            for method, path, body in [("POST", THREADS, {}), ("GET", THREADS, None), *thread_requests(thread_id)]:
                with self.subTest(method=method, path=path, credential_present=bool(credential)):
                    res = await self.client.request(method, path, headers=headers, json=body)
                    self.assertEqual(res.status_code, 401, res.text)
                    self.assertEqual(res.headers["WWW-Authenticate"], "Bearer")
                    self.assertEqual(res.headers["content-type"], "application/json")
                    self.assertEqual(res.json()["code"], "UNAUTHORIZED")
        self.assertEqual(await self.snapshot(), before)
        self.agent.astream_events.assert_not_called()
        self.agent.aget_state.assert_not_called()
        self.agent.checkpointer.adelete_thread.assert_not_called()

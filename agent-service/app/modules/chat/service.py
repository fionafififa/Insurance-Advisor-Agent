from fastapi.sse import ServerSentEvent
from langchain.messages import HumanMessage
from langchain_core.messages import AIMessage
from langgraph.graph.state import CompiledStateGraph
from .schema import ChatRequest


class ChatService:

    def __init__(self, agent: CompiledStateGraph):
        self.agent = agent

    async def chat_stream(self, request: ChatRequest):
        """为已通过归属校验的会话生成 SSE 事件。"""
        _input = {"messages": [HumanMessage(request.message)]}

        config = {"configurable": {"thread_id": str(request.thread_id)}}

        stream = await self.agent.astream_events(
            _input,
            config,
            version="v3"
        )

        async for event in stream:
            method = event['method']
            # 判断事件类型，可以是messages、interrupts等等
            if method == 'messages':
                data = event['params']['data'][0]
                if isinstance(data, AIMessage):
                    yield ServerSentEvent(data=data.text, event="message")
                elif data.get('delta') and data['delta'].get('text'):
                    yield ServerSentEvent(data=data['delta'].get('text'), event="message")

        yield ServerSentEvent(data="END", event="done")

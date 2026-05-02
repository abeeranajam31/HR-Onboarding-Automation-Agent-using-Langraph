from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from schema import ChatRequest, ChatResponse
from secured_graph import build_secured_graph

PROJECT_ROOT = Path(__file__).resolve().parent
CHECKPOINT_DB = Path(os.getenv("CHECKPOINT_DB_PATH", PROJECT_ROOT / "checkpoint_db.sqlite"))

def _message_text(message: BaseMessage | Any) -> str:
    if isinstance(message, BaseMessage):
        return str(message.content)
    return str(message)


def _extract_answer(result: dict[str, Any]) -> str:
    messages = result.get("messages", [])
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            text = str(message.content).strip()
            if text:
                return text
    if messages:
        return _message_text(messages[-1])
    return "No answer generated."


def _thread_id_value(thread_id: Any) -> str:
    return str(thread_id)


def _state_for_message(message: str) -> dict[str, Any]:
    return {"messages": [HumanMessage(content=message)], "trace": []}


def _sse_payload(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, default=str)
    return f"event: {event}\ndata: {payload}\n\n"

#Global checkpointer 
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncSqliteSaver.from_conn_string(str(CHECKPOINT_DB)) as checkpointer:
        app.state.graph = build_secured_graph(checkpointer=checkpointer)
        yield


app = FastAPI(title="HR Onboarding Agent API", lifespan=lifespan)


def _graph(request: Request):
    return request.app.state.graph


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, http_request: Request) -> ChatResponse:
    graph = _graph(http_request)
    config = {"configurable": {"thread_id": _thread_id_value(request.thread_id)}}
    #Converts HTTP request → graph state
    result = await graph.ainvoke(_state_for_message(request.message), config=config)
    return ChatResponse(
        answer=_extract_answer(result),
        status="completed",
        thread_id=_thread_id_value(request.thread_id),
    )


async def _stream_graph(graph, request: ChatRequest) -> AsyncIterator[str]:
    config = {"configurable": {"thread_id": _thread_id_value(request.thread_id)}}
    async for chunk in graph.astream(_state_for_message(request.message), config=config):
        data = {
            "thread_id": _thread_id_value(request.thread_id),
            "chunk": chunk,
        }
        yield _sse_payload("chunk", data)

    state = await graph.aget_state(config)
    final_answer = ""
    if state and state.values:
        final_answer = _extract_answer(state.values)
    yield _sse_payload(
        "done",
        {
            "thread_id": _thread_id_value(request.thread_id),
            "status": "completed",
            "answer": final_answer,
        },
    )


@app.post("/stream")
async def stream(request: ChatRequest, http_request: Request):
    graph = _graph(http_request)
    return StreamingResponse(_stream_graph(graph, request), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)

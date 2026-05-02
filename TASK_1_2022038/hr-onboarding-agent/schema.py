from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    thread_id: UUID | str = Field(min_length=1)


class ChatResponse(BaseModel):
    answer: str
    status: str
    thread_id: str

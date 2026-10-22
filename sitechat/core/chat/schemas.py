from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field


@dataclass
class ChatEvent:
    kind: Literal["status", "token", "sources", "error"]
    text: str = ""
    sources: list[dict] = field(default_factory=list)


class ChatTitle(BaseModel):
    title: str = Field(
        description="Short chat title, at most 60 characters, plain text",
        min_length=1,
        max_length=60,
    )


class ChatSummary(BaseModel):
    summary: str = Field(
        description="Running summary of the conversation, at most 500 words",
        min_length=1,
    )

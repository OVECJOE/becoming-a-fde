from pydantic import BaseModel, Field


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

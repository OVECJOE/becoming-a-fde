from collections.abc import AsyncGenerator, Sequence

import openai
from chromadb import Collection
from dotenv import load_dotenv

from core.chat.embedder import retrieve_relevant_chunks
from core.chat.prompts import CHAT_SYSTEM_PROMPT
from core.chat.schemas import ChatEvent
from core.config import settings

load_dotenv()
chat_client = openai.AsyncOpenAI(
    timeout=settings.openai_timeout_seconds,
    max_retries=settings.openai_max_retries,
)


def _build_question(
    question: str,
    summary: str | None,
    recent: Sequence[tuple[str, str]],
) -> str:
    parts = []
    if summary:
        parts.append(f"<history>\n{summary}\n</history>")
    for user_msg, ai_msg in recent:
        parts.append(f"Earlier user: {user_msg}\nEarlier assistant: {ai_msg}")
    parts.append(f"Question: {question}")
    return "\n\n".join(parts)


def _build_system_prompt(site: str | None) -> str:
    if not site:
        return CHAT_SYSTEM_PROMPT
    return f"{CHAT_SYSTEM_PROMPT}\nThe content was crawled from the website '{site}'.\n"


async def chat(
    collection: Collection,
    question: str,
    site_id: int | None = None,
    site: str | None = None,
    summary: str | None = None,
    recent: Sequence[tuple[str, str]] = (),
) -> AsyncGenerator[ChatEvent, None]:
    label = f" '{site}'" if site else ""
    yield ChatEvent("status", f"Searching the knowledge base{label}...")
    try:
        chunks = await retrieve_relevant_chunks(
            collection, question, site_id=site_id
        )
    except openai.APIError as e:
        yield ChatEvent("error", f"Failed to reach the LLM provider: {e!s}")
        return
    if not chunks:
        yield ChatEvent(
            "error",
            f"I couldn't find anything relevant{label} to answer that.",
        )
        return

    pages = {chunk["page_url"] for chunk in chunks}
    yield ChatEvent(
        "status",
        f"Found {len(chunks)} chunks from {len(pages)} pages; answering...",
    )
    context = "\n\n".join(chunk["text"] for chunk in chunks)
    streamed: list[str] = []
    try:
        stream = await chat_client.chat.completions.create(
            model="gpt-5-mini-2025-08-07",
            max_completion_tokens=1000,
            reasoning_effort="low",
            messages=[
                {"role": "system", "content": _build_system_prompt(site)},
                {
                    "role": "user",
                    "content": f"<context>\n{context}\n</context>\n\n{_build_question(question, summary, recent)}",
                },
            ],
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                streamed.append(delta)
                yield ChatEvent("token", delta)
    except openai.APIError as e:
        if streamed:
            yield ChatEvent(
                "error",
                f"\n[stream interrupted: {e!s}; answer may be incomplete]",
            )
        else:
            yield ChatEvent("error", f"Failed to reach the LLM provider: {e!s}")
        return
    yield ChatEvent("sources", sources=chunks)

from datetime import UTC, datetime

import aiosqlite
import httpx
import openai
from dotenv import load_dotenv

from core.chat.prompts import (
    SUMMARY_SYSTEM_PROMPT,
    SUMMARY_USER_TEMPLATE,
    TITLE_SYSTEM_PROMPT,
    TITLE_USER_TEMPLATE,
)
from core.chat.schemas import ChatSummary, ChatTitle
from core.db.repository import (
    append_message,
    count_exchanges,
    create_chat,
    get_first_exchange,
    get_history,
    get_recent_exchanges,
    touch_chat,
    update_chat_history,
    update_chat_title,
)

load_dotenv()
structured_client = openai.AsyncOpenAI()

SUMMARY_EVERY = 5
RECENT_FOR_PROMPT = 3
UNTITLED_PREFIX = "Untitled chat"


async def open_new_chat(db: aiosqlite.Connection, title: str | None = None) -> dict:
    if title:
        chat_id = await create_chat(db, title)
        return {"id": chat_id, "title": title}
    provisional = (
        f"{UNTITLED_PREFIX} {datetime.now(UTC).isoformat(timespec='microseconds')}"
    )
    chat_id = await create_chat(db, provisional)
    return {"id": chat_id, "title": provisional}


async def get_context(
    db: aiosqlite.Connection, chat_id: int
) -> tuple[str | None, list[tuple[str, str]]]:
    summary = await get_history(db, chat_id)
    recent = await get_recent_exchanges(db, chat_id, RECENT_FOR_PROMPT)
    return summary, recent


async def record_exchange(
    db: aiosqlite.Connection, chat_id: int, user_prompt: str, ai_response: str
) -> str:
    await append_message(db, chat_id, "user", user_prompt)
    await append_message(db, chat_id, "ai", ai_response)
    await touch_chat(db, chat_id, user_prompt, ai_response)

    exchanges = await count_exchanges(db, chat_id)
    title = await _maybe_generate_title(db, chat_id, exchanges)
    await _maybe_summarize(db, chat_id, exchanges)
    return title


async def _current_title(db: aiosqlite.Connection, chat_id: int) -> str:
    async with db.execute("SELECT title FROM chats WHERE id = ?", (chat_id,)) as cursor:
        row = await cursor.fetchone()
        assert row is not None
        return row[0]


async def _maybe_generate_title(
    db: aiosqlite.Connection, chat_id: int, exchanges: int
) -> str:
    title = await _current_title(db, chat_id)
    if exchanges != 1 or not title.startswith(UNTITLED_PREFIX):
        return title
    first = await get_first_exchange(db, chat_id)
    if first is None:
        return title
    try:
        candidate = await _generate_title(first[0], first[1])
    except (httpx.HTTPError, openai.OpenAIError):
        candidate = first[0][:60].strip() or title
    await update_chat_title(db, chat_id, await _unique_title(db, chat_id, candidate))
    return await _current_title(db, chat_id)


async def _unique_title(db: aiosqlite.Connection, chat_id: int, candidate: str) -> str:
    candidate = candidate.strip()[:60] or f"{UNTITLED_PREFIX} {chat_id}"
    async with db.execute(
        "SELECT id FROM chats WHERE title = ? COLLATE NOCASE AND id != ?",
        (candidate, chat_id),
    ) as cursor:
        if await cursor.fetchone() is None:
            return candidate
    suffix = 2
    while True:
        numbered = f"{candidate[:55].rstrip()} ({suffix})"[:60]
        async with db.execute(
            "SELECT id FROM chats WHERE title = ? COLLATE NOCASE AND id != ?",
            (numbered, chat_id),
        ) as cursor:
            if await cursor.fetchone() is None:
                return numbered
        suffix += 1


async def _generate_title(first_user: str, first_ai: str) -> str:
    response = await structured_client.chat.completions.parse(
        model="gpt-5-mini-2025-08-07",
        reasoning_effort="minimal",
        messages=[
            {"role": "system", "content": TITLE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": TITLE_USER_TEMPLATE.format(
                    first_user=first_user, first_ai=first_ai
                ),
            },
        ],
        response_format=ChatTitle,
    )
    parsed = response.choices[0].message.parsed
    assert parsed is not None
    return parsed.title


async def _maybe_summarize(
    db: aiosqlite.Connection, chat_id: int, exchanges: int
) -> None:
    if exchanges == 0 or exchanges % SUMMARY_EVERY != 0:
        return
    previous = await get_history(db, chat_id)
    latest = await get_recent_exchanges(db, chat_id, SUMMARY_EVERY)
    try:
        summary = await _generate_summary(previous, latest)
    except (httpx.HTTPError, openai.OpenAIError):
        return
    await update_chat_history(db, chat_id, summary)


async def _generate_summary(previous: str | None, latest: list[tuple[str, str]]) -> str:
    rendered = "\n\n".join(f"User: {user}\nAssistant: {ai}" for user, ai in latest)
    response = await structured_client.chat.completions.parse(
        model="gpt-5-mini-2025-08-07",
        reasoning_effort="minimal",
        messages=[
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": SUMMARY_USER_TEMPLATE.format(
                    previous=previous or "None yet.", exchanges=rendered
                ),
            },
        ],
        response_format=ChatSummary,
    )
    parsed = response.choices[0].message.parsed
    assert parsed is not None
    return parsed.summary

from datetime import UTC, datetime
from enum import StrEnum

import aiosqlite


class PageStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    CRAWLED = "crawled"
    FAILED = "failed"


async def insert_page(
    db: aiosqlite.Connection, url: str, depth: int, parent_url: str | None
):
    sql = """
        INSERT INTO pages (
            url,
            status,
            parent_url,
            depth,
            created_at
        ) VALUES (?, 'pending', ?, ?, ?)
    """
    async with db.execute(sql, (url, parent_url, depth, datetime.now(UTC))) as cursor:
        await db.commit()
        assert cursor.rowcount == 1
        return cursor.rowcount


async def fetch_pending(db: aiosqlite.Connection, limit: int):
    sql = """
        UPDATE pages SET status = 'in_progress'
        WHERE id IN (
            SELECT id FROM pages
            WHERE status = 'pending'
            ORDER BY created_at ASC
            LIMIT ?
        )
        RETURNING id, url, depth
    """
    async with db.execute(sql, (limit,)) as cursor:
        results = [
            {"id": row[0], "url": row[1], "depth": row[2]}
            for row in await cursor.fetchall()
        ]
        await db.commit()
        return results


async def mark_status(
    db: aiosqlite.Connection, url: str, status: str, crawled_at: datetime | None = None
):
    sql = """
        UPDATE pages SET status = ?, crawled_at = ?
        WHERE url = ?
    """
    await db.execute(
        sql, (status, crawled_at if status == PageStatus.CRAWLED else None, url)
    )
    await db.commit()


async def url_exists(db: aiosqlite.Connection, url: str) -> bool:
    async with db.execute(
        "SELECT COUNT(url) FROM pages WHERE url = ?", (url,)
    ) as cursor:
        result = await cursor.fetchone()
        return result[0] > 0 if result else False


async def insert_page_chunk(
    db: aiosqlite.Connection, page_id: int, chunk_index: int, chunk: str
):
    sql = """
        INSERT INTO page_chunks (
            page_id,
            content,
            chunk_index,
            created_at
        ) VALUES (?, ?, ?, ?)
    """
    async with db.execute(
        sql, (page_id, chunk, chunk_index, datetime.now(UTC))
    ) as cursor:
        row_id = cursor.lastrowid
        await db.commit()
        assert cursor.rowcount == 1
        return row_id


async def create_chat(db: aiosqlite.Connection, title: str) -> int:
    now = datetime.now(UTC)
    async with db.execute(
        "INSERT INTO chats (title, last_user_prompt, last_ai_response, created_at, updated_at) VALUES (?, '', '', ?, ?)",
        (title, now, now),
    ) as cursor:
        chat_id = cursor.lastrowid
        await db.commit()
        assert cursor.rowcount == 1
        assert chat_id is not None
        return chat_id


async def list_chats(db: aiosqlite.Connection, limit: int = 20) -> list[dict]:
    async with db.execute(
        "SELECT id, title, last_user_prompt, updated_at FROM chats ORDER BY updated_at DESC LIMIT ?",
        (limit,),
    ) as cursor:
        return [
            {
                "id": row[0],
                "title": row[1],
                "last_user_prompt": row[2],
                "updated_at": row[3],
            }
            for row in await cursor.fetchall()
        ]


async def search_chats(
    db: aiosqlite.Connection, fragment: str, limit: int = 20
) -> list[dict]:
    like = f"%{fragment}%"
    async with db.execute(
        "SELECT id, title, updated_at FROM chats WHERE title LIKE ? OR CAST(id AS TEXT) LIKE ? ORDER BY updated_at DESC LIMIT ?",
        (like, like, limit),
    ) as cursor:
        return [
            {"id": row[0], "title": row[1], "updated_at": row[2]}
            for row in await cursor.fetchall()
        ]


async def get_chat(db: aiosqlite.Connection, chat_id: int) -> dict | None:
    async with db.execute(
        "SELECT id, title FROM chats WHERE id = ?", (chat_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return {"id": row[0], "title": row[1]} if row else None


async def find_chat_by_title(db: aiosqlite.Connection, title: str) -> dict | None:
    async with db.execute(
        "SELECT id, title FROM chats WHERE title = ? COLLATE NOCASE", (title,)
    ) as cursor:
        row = await cursor.fetchone()
        return {"id": row[0], "title": row[1]} if row else None


async def append_message(
    db: aiosqlite.Connection, chat_id: int, role: str, content: str
) -> None:
    await db.execute(
        "INSERT INTO messages (chat_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (chat_id, role, content, datetime.now(UTC)),
    )
    await db.commit()


async def touch_chat(
    db: aiosqlite.Connection, chat_id: int, last_user_prompt: str, last_ai_response: str
) -> None:
    await db.execute(
        "UPDATE chats SET last_user_prompt = ?, last_ai_response = ?, updated_at = ? WHERE id = ?",
        (last_user_prompt, last_ai_response, datetime.now(UTC), chat_id),
    )
    await db.commit()


async def get_history(db: aiosqlite.Connection, chat_id: int) -> str | None:
    async with db.execute(
        "SELECT history FROM chats WHERE id = ?", (chat_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else None


async def update_chat_title(db: aiosqlite.Connection, chat_id: int, title: str) -> None:
    await db.execute(
        "UPDATE chats SET title = ?, updated_at = ? WHERE id = ?",
        (title, datetime.now(UTC), chat_id),
    )
    await db.commit()


async def update_chat_history(
    db: aiosqlite.Connection, chat_id: int, history: str
) -> None:
    await db.execute(
        "UPDATE chats SET history = ?, updated_at = ? WHERE id = ?",
        (history, datetime.now(UTC), chat_id),
    )
    await db.commit()


async def count_exchanges(db: aiosqlite.Connection, chat_id: int) -> int:
    async with db.execute(
        "SELECT COUNT(*) FROM messages WHERE chat_id = ? AND role = 'user'",
        (chat_id,),
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_first_exchange(
    db: aiosqlite.Connection, chat_id: int
) -> tuple[str, str] | None:
    async with db.execute(
        "SELECT content FROM messages WHERE chat_id = ? AND role = 'user' ORDER BY id ASC LIMIT 1",
        (chat_id,),
    ) as cursor:
        user_row = await cursor.fetchone()
    if user_row is None:
        return None
    async with db.execute(
        "SELECT content FROM messages WHERE chat_id = ? AND role = 'ai' ORDER BY id ASC LIMIT 1",
        (chat_id,),
    ) as cursor:
        ai_row = await cursor.fetchone()
    if ai_row is None:
        return None
    return (user_row[0], ai_row[0])


async def get_recent_exchanges(
    db: aiosqlite.Connection, chat_id: int, n: int
) -> list[tuple[str, str]]:
    async with db.execute(
        "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
        (chat_id, 2 * n),
    ) as cursor:
        rows = list(await cursor.fetchall())
    rows.reverse()
    exchanges: list[tuple[str, str]] = []
    pending_user: str | None = None
    for role, content in rows:
        if role == "user":
            pending_user = content
        elif role == "ai" and pending_user is not None:
            exchanges.append((pending_user, content))
            pending_user = None
    return exchanges[-n:] if len(exchanges) > n else exchanges

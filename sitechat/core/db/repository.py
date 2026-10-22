from datetime import UTC, datetime
from enum import StrEnum
from typing import Iterable

import aiosqlite

from core.urls import normalize_host, normalize_url


class PageStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    CRAWLED = "crawled"
    FAILED = "failed"


async def get_or_create_site(db: aiosqlite.Connection, domain: str) -> dict:
    normalized = normalize_host(domain)
    now = datetime.now(UTC)
    await db.execute(
        "INSERT OR IGNORE INTO sites (domain, created_at) VALUES (?, ?)",
        (normalized, now),
    )
    await db.commit()
    async with db.execute(
        "SELECT id, domain FROM sites WHERE domain = ?", (normalized,)
    ) as cursor:
        row = await cursor.fetchone()
    assert row is not None
    return {"id": row[0], "domain": row[1]}


async def list_sites(db: aiosqlite.Connection) -> list[dict]:
    sql = """
        SELECT s.id, s.domain, COUNT(p.id), COALESCE(SUM(p.status = 'crawled'), 0)
        FROM sites s
        LEFT JOIN pages p ON p.site_id = s.id
        GROUP BY s.id
        ORDER BY s.domain ASC
    """
    async with db.execute(sql) as cursor:
        return [
            {
                "id": row[0],
                "domain": row[1],
                "page_count": row[2],
                "crawled_count": row[3],
            }
            for row in await cursor.fetchall()
        ]


async def recover_stale_pages(db: aiosqlite.Connection) -> int:
    cursor = await db.execute(
        "UPDATE pages SET status = 'pending' WHERE status = 'in_progress'"
    )
    await db.commit()
    return cursor.rowcount


async def count_site_pages(db: aiosqlite.Connection, site_id: int) -> int:
    async with db.execute(
        "SELECT COUNT(*) FROM pages WHERE site_id = ? AND status = 'crawled'",
        (site_id,),
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0


async def insert_pages(
    db: aiosqlite.Connection,
    site_id: int,
    entries: Iterable[tuple[str, int, str | None]],
) -> int:
    now = datetime.now(UTC)
    rows = {
        (site_id, normalize_url(url), normalize_url(parent) if parent else None, depth, now)
        for url, depth, parent in entries
    }
    if not rows:
        return 0
    sql = """
        INSERT OR IGNORE INTO pages (
            site_id,
            url,
            status,
            parent_url,
            depth,
            created_at
        ) VALUES (?, ?, 'pending', ?, ?, ?)
    """
    async with db.executemany(sql, rows) as cursor:
        await db.commit()
        return cursor.rowcount


async def fetch_pending(
    db: aiosqlite.Connection, site_id: int, limit: int
) -> list[dict]:
    sql = """
        UPDATE pages SET status = 'in_progress'
        WHERE id IN (
            SELECT id FROM pages
            WHERE site_id = ? AND status = 'pending'
            ORDER BY id ASC
            LIMIT ?
        )
        RETURNING id, url, depth
    """
    async with db.execute(sql, (site_id, limit)) as cursor:
        rows = await cursor.fetchall()
    await db.commit()
    return [
        {"id": row[0], "url": row[1], "depth": row[2]} for row in rows
    ]


async def mark_pages(
    db: aiosqlite.Connection, updates: list[tuple[int, str, datetime | None]]
) -> None:
    sql = """
        UPDATE pages SET status = ?, crawled_at = ?
        WHERE id = ?
    """
    async with db.executemany(sql, [(s, c, i) for i, s, c in updates]) as cursor:
        await db.commit()


async def insert_page_chunks(
    db: aiosqlite.Connection, rows: list[tuple[int, int, str]]
) -> list[int]:
    if not rows:
        return []
    now = datetime.now(UTC)
    placeholders = ",".join(["(?, ?, ?, ?)"] * len(rows))
    sql = f"""
        INSERT INTO page_chunks (
            page_id,
            content,
            chunk_index,
            created_at
        ) VALUES {placeholders}
        RETURNING id
    """
    params = [
        value
        for page_id, index, content in rows
        for value in (page_id, content, index, now)
    ]
    async with db.execute(sql, params) as cursor:
        ids = [row[0] for row in await cursor.fetchall()]
    await db.commit()
    return ids


async def create_chat(
    db: aiosqlite.Connection, title: str, site_id: int | None = None
) -> int:
    now = datetime.now(UTC)
    async with db.execute(
        "INSERT INTO chats (title, site_id, last_user_prompt, last_ai_response, created_at, updated_at) VALUES (?, ?, '', ?, ?, ?)",
        (title, site_id, now, now, now),
    ) as cursor:
        chat_id = cursor.lastrowid
        await db.commit()
        assert cursor.rowcount == 1
        assert chat_id is not None
        return chat_id


async def list_chats(db: aiosqlite.Connection, limit: int = 20) -> list[dict]:
    sql = """
        SELECT c.id, c.title, c.last_user_prompt, c.updated_at, s.domain
        FROM chats c
        LEFT JOIN sites s ON s.id = c.site_id
        ORDER BY c.updated_at DESC
        LIMIT ?
    """
    async with db.execute(sql, (limit,)) as cursor:
        return [
            {
                "id": row[0],
                "title": row[1],
                "last_user_prompt": row[2],
                "updated_at": row[3],
                "site": row[4],
            }
            for row in await cursor.fetchall()
        ]


async def search_chats(
    db: aiosqlite.Connection, fragment: str, limit: int = 20
) -> list[dict]:
    like = f"%{fragment}%"
    sql = """
        SELECT c.id, c.title, c.updated_at, s.domain
        FROM chats c
        LEFT JOIN sites s ON s.id = c.site_id
        WHERE c.title LIKE ? OR CAST(c.id AS TEXT) LIKE ?
        ORDER BY c.updated_at DESC
        LIMIT ?
    """
    async with db.execute(sql, (like, like, limit)) as cursor:
        return [
            {
                "id": row[0],
                "title": row[1],
                "updated_at": row[2],
                "site": row[3],
            }
            for row in await cursor.fetchall()
        ]


async def get_chat(db: aiosqlite.Connection, chat_id: int) -> dict | None:
    sql = """
        SELECT c.id, c.title, c.site_id, s.domain
        FROM chats c
        LEFT JOIN sites s ON s.id = c.site_id
        WHERE c.id = ?
        LIMIT 1
    """
    async with db.execute(sql, (chat_id,)) as cursor:
        row = await cursor.fetchone()
        if row is None:
            return None
        return {"id": row[0], "title": row[1], "site_id": row[2], "site": row[3]}


async def find_chat_by_title(db: aiosqlite.Connection, title: str) -> dict | None:
    sql = """
        SELECT c.id, c.title, c.site_id, s.domain
        FROM chats c
        LEFT JOIN sites s ON s.id = c.site_id
        WHERE c.title = ? COLLATE NOCASE
        LIMIT 1
    """
    async with db.execute(sql, (title,)) as cursor:
        row = await cursor.fetchone()
        if row is None:
            return None
        return {"id": row[0], "title": row[1], "site_id": row[2], "site": row[3]}


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

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
        results = [{"id": row[0], "url": row[1]} for row in await cursor.fetchall()]
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

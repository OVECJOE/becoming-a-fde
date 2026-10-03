from datetime import UTC, datetime

import aiosqlite


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
        RETURNING id, url
    """
    async with db.execute(sql, (limit,)) as cursor:
        results = [{"id": row[0], "url": row[1]} for row in await cursor.fetchall()]
        await db.commit()
        return results

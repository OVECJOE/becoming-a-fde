import re
from pathlib import Path

import aiosqlite

from core.config import settings
from core.constants import DB_MIGRATIONS_DIR


def _extract_version_prefix(name: str) -> str:
    m = re.match(r"^([a-z]\d+)", name)
    assert m is not None
    return m.group(1)


def _version_code(prefix: str) -> int:
    m = re.match(r"([a-z])(\d+)", prefix)
    assert m is not None
    return (ord(m.group(1)) - 96) * 10000 + int(m.group(2))


def pending_migrations(directory: Path, current_code: int) -> list[Path]:
    files = []
    for f in directory.iterdir():
        if not f.is_file():
            continue
        m = re.match(r"^([a-z]\d+)", f.name)
        if m and _version_code(m.group(1)) > current_code:
            files.append(f)
    return sorted(
        files, key=lambda f: _version_code(_extract_version_prefix(f.name))
    )


async def _has_table(db: aiosqlite.Connection, table: str) -> bool:
    cursor = await db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    )
    return await cursor.fetchone() is not None


async def _table_columns(db: aiosqlite.Connection, table: str) -> set[str]:
    cursor = await db.execute(f"PRAGMA table_info({table})")
    rows = await cursor.fetchall()
    return {row[1] for row in rows}


async def _detect_version_code(db: aiosqlite.Connection) -> int:
    if not await _has_table(db, "pages"):
        return 0
    if not await _has_table(db, "page_chunks"):
        return _version_code("a1")
    if not await _has_table(db, "chats"):
        return _version_code("a2")
    if "site_id" not in await _table_columns(db, "pages"):
        return _version_code("a3")
    if "site_id" not in await _table_columns(db, "chats"):
        return _version_code("b1")
    cursor = await db.execute("PRAGMA index_list(chats)")
    indexes = await cursor.fetchall()
    if any(row[3] == "u" for row in indexes):
        return _version_code("c1")
    return _version_code("c2")


async def init_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(settings.db_path)
    await db.execute("PRAGMA journal_mode = WAL")
    await db.execute("PRAGMA synchronous = NORMAL")
    await db.execute("PRAGMA foreign_keys = ON")
    await db.execute("PRAGMA busy_timeout = 5000")
    await db.execute("PRAGMA temp_store = MEMORY")
    await db.execute("PRAGMA cache_size = -64000")
    return db

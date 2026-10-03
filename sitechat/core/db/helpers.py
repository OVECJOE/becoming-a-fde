import json
import re
from pathlib import Path

import aiosqlite

from core.constants import DATABASE_URL, DB_MIGRATIONS_DIR


def _version_key(version: str) -> tuple[str, int]:
    """'c100' -> ('c', 100)"""
    m = re.match(r"([a-z])(\d+)", version)
    assert m is not None
    return (m.group(1), int(m.group(2)))


def _extract_version_prefix(s: str) -> str:
    m = re.match(r"^([a-z]\d+)", s)
    assert m is not None
    return m.group(1)


def newer_files(dir: Path, current: str) -> list[Path]:
    """Files in `dir` whose prefix (representing its version) is strictly greater than `current`."""
    threshold = _version_key(current)
    results = []
    for f in dir.iterdir():
        if not f.is_file():
            continue
        m = re.match(r"^([a-z]\d+)", f.name)
        if m and _version_key(m.group(1)) > threshold:
            results.append(f)
    return sorted(results, key=lambda f: _version_key(_extract_version_prefix(f.name)))


def load_config():
    config_path = DB_MIGRATIONS_DIR.joinpath(".config.json")
    with open(config_path, "r") as f:
        return json.load(f)


def save_config(new_config: dict[str, int | str]):
    config_path = DB_MIGRATIONS_DIR.joinpath(".config.json")
    with open(config_path, "w") as f:
        json.dump(new_config, f, indent=2)


def init_db() -> aiosqlite.Connection:
    return aiosqlite.connect(DATABASE_URL)


async def apply_migrations(
    db: aiosqlite.Connection, current_version: str
) -> tuple[int, str] | None:
    new_ones = newer_files(DB_MIGRATIONS_DIR, current_version)
    migration_count = len(new_ones)
    if migration_count == 0:
        return None

    for file_path in new_ones:
        with open(file_path, "r") as f:
            await db.executescript(f.read())
            await db.commit()
    return migration_count, _extract_version_prefix(new_ones[-1].name)

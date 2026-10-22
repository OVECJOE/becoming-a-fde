import aiosqlite

from core.config import settings
from core.constants import DB_MIGRATIONS_DIR
from core.db.helpers import (
    _detect_version_code,
    _extract_version_prefix,
    _version_code,
    pending_migrations,
)


async def setup_db():
    print("Checking for pending migrations...")
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cursor = await db.execute("PRAGMA user_version")
        row = await cursor.fetchone()
        current = row[0] if row else 0
        if current == 0:
            current = await _detect_version_code(db)
            await db.execute(f"PRAGMA user_version = {current}")
            await db.commit()

        new_ones = pending_migrations(DB_MIGRATIONS_DIR, current)
        if not new_ones:
            print("Database is up to date.")
            print("Database setup complete.")
            return

        print(f"Applying {len(new_ones)} migrations...")
        for file_path in new_ones:
            print(f"Applying {file_path.name}...")
            with open(file_path, "r") as f:
                await db.executescript(f.read())
            code = _version_code(_extract_version_prefix(file_path.name))
            await db.execute(f"PRAGMA user_version = {code}")
            await db.commit()
            print(f"Applied {file_path.name}.")
        print(
            f"Applied {len(new_ones)} migrations, now at {_extract_version_prefix(new_ones[-1].name)}."
        )
    print("Database setup complete.")

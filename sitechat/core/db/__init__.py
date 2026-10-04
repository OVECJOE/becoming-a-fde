import aiosqlite

from core.constants import DATABASE_URL
from core.db.helpers import apply_migrations, load_config, save_config


async def setup_db():
    print("Checking for pending migrations...")
    config = load_config()
    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        stats = await apply_migrations(db, config["current_version"])

        if stats:
            print(f"Applied {stats[0]} migrations, now at {stats[1]}.")
            config["migration_count"] += stats[0]
            config["current_version"] = stats[1]
            save_config(config)
        else:
            print("Database is up to date.")
    print("Database setup complete.")

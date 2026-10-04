from core.db.helpers import apply_migrations, init_db, load_config, save_config


async def setup_db():
    config = load_config()
    async with await init_db() as db:
        stats = await apply_migrations(
            db, config["current_version"]
        )

        if stats:
            config["migration_count"] += stats[0]
            config["current_version"] = stats[1]
            save_config(config)

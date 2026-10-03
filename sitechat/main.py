import asyncio

from core.db import setup_db
from core.db.helpers import init_db


async def main():
    await setup_db()
    db = await init_db()

    async with db.execute("PRAGMA index_list(pages)") as cursor:
        async for row in cursor:
            print(row)

    await db.close()


if __name__ == "__main__":
    asyncio.run(main())

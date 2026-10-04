import asyncio

from core.crawler import crawl
from core.db import setup_db
from core.db.helpers import init_db
from schemas import UserCommand


def parse_command(input_: str) -> UserCommand:
    command, args = input_.split(None, 1)
    return UserCommand(
        command=command.lower(),
        args=args.split()
    )


async def main():
    await setup_db()
    db = await init_db()

    while True:
        user_input = await asyncio.to_thread(input, "sitechat> ")
        command = parse_command(user_input)
        if command.command == "crawl":
            await crawl(db, command.args[0])
        elif command.command == "chat":
            pass
        else:
            break

    await db.close()


if __name__ == "__main__":
    asyncio.run(main())

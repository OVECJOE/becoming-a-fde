import asyncio
import re
import shlex
import sqlite3
from typing import ClassVar
from urllib.parse import urlparse

import aiosqlite
import chromadb
from chromadb import Collection
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion, WordCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style
from pygments.lexer import RegexLexer
from pygments.token import Keyword, Text
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from core.chat import chat, get_context, open_new_chat, record_exchange
from core.constants import DATABASE_URL, PROJECT_ROOT
from core.crawler import crawl
from core.db import setup_db
from core.db.helpers import init_db
from core.db.repository import (
    find_chat_by_title,
    get_chat,
    list_chats,
    search_chats,
)
from schemas import UserCommand

console = Console()

COMMANDS = ["crawl", "chat", "help", "exit"]
COMMAND_META = {
    "crawl": "crawl a site: crawl <domain>",
    "chat": "open a chat: chat <chat-id>",
    "help": "show this help",
    "exit": "quit (quit, q also work)",
}


class SitechatLexer(RegexLexer):
    name = "sitechat"
    aliases = ("sitechat",)
    flags = re.IGNORECASE
    tokens: ClassVar[dict] = {
        "root": [
            (r"\s+", Text),
            (r"(crawl|chat|help|exit|quit|q|clear)\b", Keyword, "args"),
            (r"\S+", Text, "args"),
        ],
        "args": [
            (r"\s+", Text),
            (r".+", Text),
        ],
    }


APP_STYLE = Style.from_dict(
    {
        "prompt": "bold ansicyan",
        "pygments.keyword": "bold ansimagenta",
        "pygments.text": "ansiyellow",
        "bottom-toolbar": "bg:#333333 #ffffff",
    }
)


def _read_chats_sync(fragment: str, limit: int = 20) -> list[dict]:
    try:
        con = sqlite3.connect(str(DATABASE_URL))
    except sqlite3.Error:
        return []
    try:
        cur = con.execute(
            "SELECT id, title FROM chats WHERE title LIKE ? OR CAST(id AS TEXT) LIKE ? ORDER BY updated_at DESC LIMIT ?",
            (f"%{fragment}%", f"%{fragment}%", limit),
        )
        return [{"id": row[0], "title": row[1]} for row in cur.fetchall()]
    except sqlite3.Error:
        return []
    finally:
        con.close()


class SitechatCompleter(Completer):
    def __init__(self) -> None:
        self._commands = WordCompleter(
            COMMANDS + ["quit", "q", "clear"],
            meta_dict={
                **COMMAND_META,
                "quit": "quit",
                "q": "quit",
                "clear": "clear screen",
            },
            ignore_case=True,
        )

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        head, _, rest = text.partition(" ")
        if not rest and " " not in text:
            yield from self._commands.get_completions(document, complete_event)
            return
        if head.lower() != "chat":
            return
        fragment = rest.lstrip()
        for row in _read_chats_sync(fragment):
            yield Completion(
                str(row["id"]),
                start_position=-len(fragment),
                display=f"{row['title']}  [{row['id']}]",
                display_meta="chat",
            )


session = PromptSession(
    history=InMemoryHistory(),
    completer=SitechatCompleter(),
    lexer=PygmentsLexer(SitechatLexer),
    style=APP_STYLE,
    complete_while_typing=True,
)

chat_session = PromptSession(
    history=InMemoryHistory(),
    style=APP_STYLE,
    complete_while_typing=False,
)


def _normalize_domain(raw: str) -> str:
    candidate = raw.strip().strip("/")
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    host = urlparse(candidate).netloc or urlparse(candidate).path
    return host.split("/")[0].strip().lower()


def _parse_command(raw: str) -> UserCommand | None:
    text = raw.strip()
    if not text:
        return None
    head, _, rest = text.partition(" ")
    command = head.lower()
    rest = rest.strip()
    if command in ("q", "quit"):
        return UserCommand(command="exit", args="")
    if command == "clear":
        return UserCommand(command="clear", args="")
    if command in ("crawl", "chat", "help", "exit"):
        if command == "crawl":
            try:
                parts = shlex.split(rest)
            except ValueError:
                parts = rest.split()
            if len(parts) != 1:
                raise ValueError("Usage: crawl <domain>")
            return UserCommand(command=command, args=_normalize_domain(parts[0]))
        if command == "chat":
            if not rest:
                return UserCommand(command="chat", args="")
            if (
                rest.lower() == "new"
                or rest.lower().startswith("new ")
                or rest.lower().startswith("new:")
            ):
                return UserCommand(command=command, args=rest)
            try:
                parts = shlex.split(rest)
            except ValueError:
                parts = rest.split()
            if len(parts) != 1:
                raise ValueError("Usage: chat <chat-id>")
            return UserCommand(command=command, args=parts[0])
        return UserCommand(command=command, args=rest)
    try:
        guess = shlex.split(text)
    except ValueError:
        guess = text.split()
    raise ValueError(f"Unknown command {guess[0]!r}. Type 'help' to see commands.")


def _print_welcome() -> None:
    console.print(
        Panel.fit(
            "[bold cyan]sitechat[/]  crawl a site, then chat with it.\n"
            "[magenta]crawl[/] [yellow]<domain>[/]   [dim]e.g. crawl example.com[/]\n"
            "[magenta]chat[/] [yellow]<chat-id>[/]  [dim]e.g. chat 1 (titles autocomplete as you type)[/]",
            title="welcome",
            border_style="cyan",
        )
    )


def _print_help() -> None:
    table = Table(title="Commands", show_header=True, header_style="bold cyan")
    table.add_column("Command", style="magenta", no_wrap=True)
    table.add_column("Args", style="yellow")
    table.add_column("Example", style="dim")
    table.add_row("crawl", "<domain>", "crawl example.com")
    table.add_row("chat", "<chat-id>", "chat 1  (leave empty to list chats)")
    table.add_row("chat new", "[title]", "chat new  (title auto-generated)")
    table.add_row("help", "", "help")
    table.add_row("exit", "", "exit  (quit, q also work)")
    console.print(table)
    console.print(
        "[dim]Inside a chat: just type to ask. /exit or Ctrl-C returns here.[/dim]"
    )


def _print_chats(chats: list[dict]) -> None:
    if not chats:
        console.print("[yellow]No chats yet. Type: chat new <title>[/yellow]")
        return
    table = Table(title="Chats", show_header=True, header_style="bold cyan")
    table.add_column("ID", style="magenta", no_wrap=True)
    table.add_column("Title", style="yellow")
    table.add_column("Last prompt", style="dim")
    for row in chats:
        table.add_row(
            str(row["id"]), row["title"], (row.get("last_user_prompt") or "")[:60]
        )
    console.print(table)


async def _resolve_chat(db: aiosqlite.Connection, arg: str) -> dict | None:
    if arg.isdigit():
        return await get_chat(db, int(arg))
    return await find_chat_by_title(db, arg)


async def _chat_session(
    db: aiosqlite.Connection, collection: Collection, chat_id: int, title: str
) -> None:
    console.print(
        f"[green]Chatting in '{title}' [{chat_id}]. Type /exit to leave.[/green]"
    )
    while True:
        try:
            with patch_stdout():
                question = await chat_session.prompt_async(
                    HTML(f"<prompt>chat '{title}'</prompt>> "),
                    placeholder=HTML("ask anything, /exit to leave"),
                )
        except (EOFError, KeyboardInterrupt):
            break
        text = question.strip()
        if not text:
            continue
        if text.lower() in ("/exit", "/quit", "/q", "exit", "quit"):
            break
        if text.lower() in ("/help", "help"):
            console.print("[dim]Just type a question. /exit leaves this chat.[/dim]")
            continue
        console.print("[cyan]Answering...[/cyan]")
        summary, recent = await get_context(db, chat_id)
        chunks: list[str] = []
        async for token in chat(collection, text, summary=summary, recent=recent):
            chunks.append(token)
            print(token, end="", flush=True)
        print()
        answer = "".join(chunks)
        title = await record_exchange(db, chat_id, text, answer)
    console.print(f"[dim]Left chat '{title}'.[/dim]")


async def _startup():
    console.print("[dim]Setting up database...[/dim]")
    await setup_db()

    console.print("[dim]Connecting to database...[/dim]")
    db = await init_db()

    console.print("[dim]Setting up chromadb persistent client...[/dim]")
    client = chromadb.PersistentClient(path=PROJECT_ROOT.joinpath(".chromadb-data"))
    collection = client.get_or_create_collection(
        name="sitechat_chunks", metadata={"hnsw:space": "cosine"}
    )
    console.print("[green]Setup complete![/green]")
    _print_welcome()

    return db, collection


def _bottom_toolbar():
    return HTML(
        " <b>crawl</b> &lt;domain&gt;  |  <b>chat</b> &lt;chat-id&gt;  |  <b>help</b>  |  <b>exit</b>"
    )


async def main():
    db, collection = await _startup()

    while True:
        try:
            with patch_stdout():
                user_input = await session.prompt_async(
                    HTML("<prompt>\nsitechat</prompt>> "),
                    placeholder=HTML("crawl example.com  or  chat 1"),
                    bottom_toolbar=_bottom_toolbar,
                )
        except (EOFError, KeyboardInterrupt):
            break
        try:
            command = _parse_command(user_input)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            continue
        if command is None:
            continue
        if command.command == "crawl":
            console.print(f"[cyan]Starting crawl for {command.args}...[/cyan]")
            await crawl(db, collection, command.args)
            console.print(f"[green]Crawl started for {command.args}.[/green]")
        elif command.command == "chat":
            if not command.args:
                _print_chats(await list_chats(db))
                continue
            if command.args.lower() == "new":
                created = await open_new_chat(db)
                console.print(
                    f"[green]Created chat '{created['title']}' [{created['id']}].[/green]"
                )
                await _chat_session(db, collection, created["id"], created["title"])
                continue
            if command.args.lower().startswith(
                "new "
            ) or command.args.lower().startswith("new:"):
                title = command.args[3:].strip(" :")
                if not title:
                    console.print("[red]Usage: chat new <title>[/red]")
                    continue
                existing = await find_chat_by_title(db, title)
                if existing:
                    await _chat_session(
                        db, collection, existing["id"], existing["title"]
                    )
                else:
                    created = await open_new_chat(db, title)
                    console.print(
                        f"[green]Created chat '{title}' [{created['id']}].[/green]"
                    )
                    await _chat_session(db, collection, created["id"], title)
                continue
            row = await _resolve_chat(db, command.args)
            if row is None:
                found = await search_chats(db, command.args)
                if len(found) == 1:
                    row = {"id": found[0]["id"], "title": found[0]["title"]}
                elif found:
                    _print_chats(
                        [
                            {"id": r["id"], "title": r["title"], "last_user_prompt": ""}
                            for r in found
                        ]
                    )
                    continue
                else:
                    console.print(
                        f"[red]No chat {command.args!r}. Type 'chat' to list, or 'chat new <title>'.[/red]"
                    )
                    continue
            await _chat_session(db, collection, row["id"], row["title"])
        elif command.command == "help":
            _print_help()
        elif command.command == "clear":
            console.clear()
        else:
            break

    console.print("[dim]Closing database...[/dim]")
    await db.close()
    console.print("[dim]Done.[/dim]")


if __name__ == "__main__":
    asyncio.run(main())

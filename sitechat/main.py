import asyncio
import re
import shlex
from typing import ClassVar
from urllib.parse import urlparse

import chromadb
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
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

from core import chat
from core.constants import PROJECT_ROOT
from core.crawler import crawl
from core.db import setup_db
from core.db.helpers import init_db
from schemas import UserCommand

console = Console()

COMMANDS = ["crawl", "chat", "help", "exit"]
COMMAND_META = {
    "crawl": "crawl a site: crawl <domain>",
    "chat": "ask a question: chat <question>",
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

completer = WordCompleter(
    COMMANDS + ["quit", "q", "clear"],
    meta_dict={**COMMAND_META, "quit": "quit", "q": "quit", "clear": "clear screen"},
    ignore_case=True,
)

session = PromptSession(
    history=InMemoryHistory(),
    completer=completer,
    lexer=PygmentsLexer(SitechatLexer),
    style=APP_STYLE,
    complete_while_typing=True,
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
                raise ValueError("Usage: chat <question>")
            try:
                parts = shlex.split(rest)
                question = (
                    " ".join(parts) if len(parts) > 1 else parts[0] if parts else rest
                )
            except ValueError:
                question = rest
            if not question.strip():
                raise ValueError("Usage: chat <question>")
            return UserCommand(command=command, args=question.strip())
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
            "[magenta]chat[/] [yellow]<question>[/]  [dim]e.g. chat what does this site sell?[/]",
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
    table.add_row("chat", "<question>", "chat what is the refund policy?")
    table.add_row("help", "", "help")
    table.add_row("exit", "", "exit  (quit, q also work)")
    console.print(table)


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
        " <b>crawl</b> &lt;domain&gt;  |  <b>chat</b> &lt;question&gt;  |  <b>help</b>  |  <b>exit</b>"
    )


async def main():
    db, collection = await _startup()

    while True:
        try:
            with patch_stdout():
                user_input = await session.prompt_async(
                    HTML("<prompt>\nsitechat</prompt>> "),
                    placeholder=HTML(
                        "crawl example.com  or  chat what is this site about?"
                    ),
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
            console.print("[cyan]Answering...[/cyan]")
            async for token in chat(collection, command.args):
                print(token, end="", flush=True)
            print()
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

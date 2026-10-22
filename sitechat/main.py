import asyncio
import re
import shlex
import sqlite3
from html import escape as escape_html
from typing import ClassVar

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
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from core.chat import (
    backfill_chunk_sites,
    chat,
    get_context,
    open_new_chat,
    record_exchange,
)
from core.config import settings
from core.crawler import active_crawl_domains, cancel_active_crawls, crawl
from core.crawler.helpers import close_client
from core.db import setup_db
from core.db.helpers import init_db
from core.db.repository import (
    count_site_pages,
    find_chat_by_title,
    get_chat,
    list_chats,
    list_sites,
    recover_stale_pages,
    search_chats,
)
from core.urls import normalize_host
from schemas import UserCommand

console = Console()

COMMANDS = ["crawl", "sites", "chat", "help", "exit"]
COMMAND_META = {
    "crawl": "crawl a site in the background: crawl <domain>",
    "sites": "list crawled sites",
    "chat": "open a chat: chat <chat-id> | chat new [site] [title]",
    "help": "show this help",
    "exit": "quit (quit, q also work)",
}
KNOWN_COMMANDS = ("crawl", "sites", "chat", "help", "exit")


class SitechatLexer(RegexLexer):
    name = "sitechat"
    aliases = ("sitechat",)
    flags = re.IGNORECASE
    tokens: ClassVar[dict] = {
        "root": [
            (r"\s+", Text),
            (r"(crawl|sites|chat|help|exit|quit|q|clear)\b", Keyword, "args"),
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
        con = sqlite3.connect(str(settings.db_path))
    except sqlite3.Error:
        return []
    try:
        cur = con.execute(
            "SELECT c.id, c.title, s.domain FROM chats c LEFT JOIN sites s ON s.id = c.site_id "
            "WHERE c.title LIKE ? OR CAST(c.id AS TEXT) LIKE ? ORDER BY c.updated_at DESC LIMIT ?",
            (f"%{fragment}%", f"%{fragment}%", limit),
        )
        return [
            {"id": row[0], "title": row[1], "site": row[2]} for row in cur.fetchall()
        ]
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
            site = row["site"] or "no site"
            yield Completion(
                str(row["id"]),
                start_position=-len(fragment),
                display=f"{row['title']}  [{row['id']}] on {site}",
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
    if command == "crawl":
        try:
            parts = shlex.split(rest)
        except ValueError:
            parts = rest.split()
        if len(parts) != 1:
            raise ValueError("Usage: crawl <domain>")
        return UserCommand(command=command, args=normalize_host(parts[0]))
    if command == "chat":
        if not rest:
            return UserCommand(command="chat", args="")
        if rest.lower() == "new" or re.match(r"^new[\s:]", rest, re.IGNORECASE):
            return UserCommand(command="chat", args=rest)
        try:
            parts = shlex.split(rest)
        except ValueError:
            parts = rest.split()
        if len(parts) != 1:
            raise ValueError("Usage: chat <chat-id>  (or: chat new [site] [title])")
        return UserCommand(command=command, args=parts[0])
    if command in KNOWN_COMMANDS:
        return UserCommand(command=command, args=rest)
    guess = shlex.split(text)
    raise ValueError(f"Unknown command {guess[0]!r}. Type 'help' to see commands.")


def _print_welcome() -> None:
    console.print(
        Panel.fit(
            "[bold cyan]sitechat[/]  crawl sites in the background, then chat with them.\n\n"
            "[magenta]crawl[/] [yellow]<domain>[/]      [dim]e.g. crawl example.com (runs in background)[/]\n"
            "[magenta]sites[/]                   [dim]list crawled sites and their progress[/]\n"
            "[magenta]chat new[/] [yellow]\\[site][/]  [dim]start a chat bound to one site[/]\n"
            "[magenta]chat[/] [yellow]<chat-id>[/]     [dim]resume a chat (ids autocomplete as you type)[/]",
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
    table.add_row("sites", "", "sites  (list crawled sites)")
    table.add_row("chat", "", "chat  (list chats)")
    table.add_row("chat new", "\\[site] \\[title]", "chat new example.com pricing docs")
    table.add_row("chat", "<chat-id>", "chat 1")
    table.add_row("help", "", "help")
    table.add_row("exit", "", "exit  (quit, q also work)")
    console.print(table)
    console.print(
        "[dim]Inside a chat: /help lists chat commands, /exit returns here.[/dim]"
    )


def _print_chat_help() -> None:
    console.print(
        "[dim]type a question to ask · /sources re-shows this answer's sources · "
        "/site shows the bound site · /exit leaves the chat[/dim]"
    )


def _print_sites(sites: list[dict]) -> None:
    if not sites:
        console.print("[yellow]No sites yet. Type: crawl example.com[/yellow]")
        return
    table = Table(title="Sites", show_header=True, header_style="bold cyan")
    table.add_column("ID", style="magenta", no_wrap=True)
    table.add_column("Domain", style="yellow")
    table.add_column("Pages", style="dim")
    table.add_column("Crawled", style="dim")
    for row in sites:
        table.add_row(
            str(row["id"]),
            row["domain"],
            str(row["page_count"]),
            str(row["crawled_count"]),
        )
    console.print(table)


def _print_chats(chats: list[dict]) -> None:
    if not chats:
        console.print("[yellow]No chats yet. Type: chat new[/yellow]")
        return
    table = Table(title="Chats", show_header=True, header_style="bold cyan")
    table.add_column("ID", style="magenta", no_wrap=True)
    table.add_column("Title", style="yellow")
    table.add_column("Site", style="cyan")
    table.add_column("Last prompt", style="dim")
    for row in chats:
        table.add_row(
            str(row["id"]),
            escape(row["title"]),
            row.get("site") or "-",
            escape((row.get("last_user_prompt") or "")[:60]),
        )
    console.print(table)


def _print_sources(sources: list[dict]) -> None:
    best: dict[str, tuple[int, float]] = {}
    for chunk in sources:
        url = chunk["page_url"]
        count, score = best.get(url, (0, 0.0))
        similarity = max(0.0, 1.0 - chunk["distance"])
        best[url] = (count + 1, max(score, similarity))
    table = Table(title="Sources", show_header=True, header_style="bold cyan")
    table.add_column("", style="dim", no_wrap=True, width=3)
    table.add_column("Page")
    table.add_column("Relevance", justify="right")
    ranked = sorted(best.items(), key=lambda item: -item[1][1])
    for rank, (url, (count, score)) in enumerate(ranked, 1):
        suffix = f"  [dim]({count} chunks)[/]" if count > 1 else ""
        table.add_row(str(rank), f"{escape(url)}{suffix}", f"{score:.0%}")
    console.print(table)


async def _resolve_chat(db: aiosqlite.Connection, arg: str) -> dict | None:
    if arg.isdigit():
        return await get_chat(db, int(arg))
    return await find_chat_by_title(db, arg)


async def _pick_site(db: aiosqlite.Connection) -> dict | None:
    sites = await list_sites(db)
    _print_sites(sites)
    completer = WordCompleter(
        [row["domain"] for row in sites] + [str(row["id"]) for row in sites],
        ignore_case=True,
    )
    while True:
        try:
            with patch_stdout():
                raw = await chat_session.prompt_async(
                    HTML("<prompt>site</prompt>> "),
                    completer=completer,
                    complete_while_typing=False,
                )
        except (EOFError, KeyboardInterrupt):
            return None
        answer = raw.strip()
        if not answer:
            return None
        match = next(
            (
                row
                for row in sites
                if answer == str(row["id"])
                or row["domain"] == answer
                or row["domain"].startswith(answer)
            ),
            None,
        )
        if match:
            return match
        console.print(
            f"[red]No site {answer!r}. Enter a domain or id from the list (empty cancels).[/red]"
        )


async def _handle_new_chat(
    db: aiosqlite.Connection, collection: Collection, rest: str
) -> None:
    sites = await list_sites(db)
    if not sites:
        console.print(
            "[yellow]No sites yet — crawl one first, e.g. crawl example.com[/yellow]"
        )
        return

    site: dict | None = None
    title = rest
    tokens = rest.split(maxsplit=1)
    if tokens:
        match = next(
            (
                row
                for row in sites
                if tokens[0] == str(row["id"]) or row["domain"] == tokens[0]
            ),
            None,
        )
        if match:
            site = match
            title = tokens[1].strip() if len(tokens) > 1 else ""

    if site is None:
        if len(sites) == 1:
            site = sites[0]
        else:
            site = await _pick_site(db)
            if site is None:
                console.print("[dim]Cancelled.[/dim]")
                return

    existing = await find_chat_by_title(db, title) if title else None
    if existing:
        console.print(
            f"[green]Opening existing chat '{escape(existing['title'])}' [{existing['id']}] "
            f"on {existing['site'] or 'no site'}.[/green]"
        )
        await _chat_session(db, collection, existing)
        return

    created = await open_new_chat(db, title or None, site["id"])
    console.print(
        f"[green]Created chat '{escape(created['title'])}' [{created['id']}] on {site['domain']}.[/green]"
    )
    await _chat_session(db, collection, created)


async def _chat_session(
    db: aiosqlite.Connection, collection: Collection, chat_row: dict
) -> None:
    chat_id = chat_row["id"]
    title = chat_row["title"]
    site = chat_row.get("site")
    site_id = chat_row.get("site_id")
    pages = await count_site_pages(db, site_id) if site_id else 0
    console.print(
        Panel.fit(
            f"[yellow]{escape(title)}[/] [dim][chat {chat_id}][/]\n"
            f"Knowledge base: [cyan]{escape(site or 'all sites')}[/] "
            f"[dim]({pages} crawled pages)[/]\n"
            "[dim]/help for commands, /exit to leave[/]",
            title="chat",
            border_style="green",
        )
    )
    last_sources: list[dict] = []
    while True:
        try:
            with patch_stdout():
                question = await chat_session.prompt_async(
                    HTML(
                        f"<prompt>{escape_html(title)} @ {escape_html(site or 'all')}</prompt>> "
                    ),
                    placeholder=HTML("ask anything, /help for commands"),
                )
        except (EOFError, KeyboardInterrupt):
            break
        text = question.strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in ("/exit", "/quit", "/q"):
            break
        if lowered in ("/help", "/h"):
            _print_chat_help()
            continue
        if lowered == "/sources":
            if last_sources:
                _print_sources(last_sources)
            else:
                console.print("[dim]No sources yet in this session.[/dim]")
            continue
        if lowered == "/site":
            console.print(
                f"[cyan]{site or 'all sites'}[/] [dim]({pages} crawled pages)[/]"
            )
            continue

        summary, recent = await get_context(db, chat_id)
        parts: list[str] = []
        failed = False
        async for event in chat(
            collection,
            text,
            site_id=site_id,
            site=site,
            summary=summary,
            recent=recent,
        ):
            if event.kind == "status":
                console.print(f"[dim]{event.text}[/dim]")
            elif event.kind == "token":
                parts.append(event.text)
                print(event.text, end="", flush=True)
            elif event.kind == "sources":
                last_sources = event.sources
                print()
                _print_sources(event.sources)
            elif event.kind == "error":
                if parts:
                    print()
                console.print(f"[red]{event.text}[/red]")
                failed = True
        if not parts or failed:
            continue
        title = await record_exchange(db, chat_id, text, "".join(parts))
    console.print(f"[dim]Left chat '{escape(title)}'.[/dim]")


async def _startup():
    console.print("[dim]Setting up database...[/dim]")
    await setup_db()

    console.print("[dim]Connecting to database...[/dim]")
    db = await init_db()

    console.print("[dim]Setting up chromadb persistent client...[/dim]")
    client = chromadb.PersistentClient(path=settings.chroma_path)
    collection = client.get_or_create_collection(
        name="sitechat_chunks", metadata={"hnsw:space": "cosine"}
    )

    recovered = await recover_stale_pages(db)
    if recovered:
        console.print(
            f"[yellow]Recovered {recovered} pages that were interrupted mid-crawl.[/yellow]"
        )
    try:
        backfilled = await backfill_chunk_sites(db, collection)
    except Exception as e:
        console.print(
            f"[yellow]Chunk site-metadata backfill skipped ({type(e).__name__}: {e}).[/yellow]"
        )
    else:
        if backfilled:
            console.print(
                f"[dim]Backfilled site metadata on {backfilled} indexed chunks.[/dim]"
            )

    console.print("[green]Setup complete![/green]")
    _print_welcome()

    return db, collection


def _bottom_toolbar():
    active = active_crawl_domains()
    prefix = (
        f" <b>crawling</b> <yellow>{escape_html(', '.join(active))}</yellow>  |"
        if active
        else ""
    )
    return HTML(
        f"{prefix} <b>crawl</b> &lt;domain&gt;  |  <b>sites</b>  |  <b>chat</b>  |  <b>help</b>  |  <b>exit</b>"
    )


async def main():
    db, collection = await _startup()

    while True:
        try:
            with patch_stdout():
                user_input = await session.prompt_async(
                    HTML("<prompt>\nsitechat</prompt>> "),
                    placeholder=HTML("crawl example.com  or  chat new"),
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
            result = await crawl(db, collection, command.args)
            if result is None:
                console.print(
                    f"[yellow]A crawl for {command.args} is already running.[/yellow]"
                )
            else:
                site, _ = result
                console.print(
                    f"[green]Crawling {site['domain']} in the background — "
                    f"type 'sites' to check progress.[/green]"
                )
        elif command.command == "sites":
            _print_sites(await list_sites(db))
        elif command.command == "chat":
            if not command.args:
                _print_chats(await list_chats(db))
                continue
            if command.args.lower() == "new" or re.match(
                r"^new[\s:]", command.args, re.IGNORECASE
            ):
                await _handle_new_chat(db, collection, command.args[3:].strip(" :"))
                continue
            row = await _resolve_chat(db, command.args)
            if row is None:
                found = await search_chats(db, command.args)
                if len(found) == 1:
                    row = await get_chat(db, found[0]["id"])
                elif found:
                    _print_chats(found)
                    continue
                else:
                    console.print(
                        f"[red]No chat {command.args!r}. Type 'chat' to list, or 'chat new'.[/red]"
                    )
                    continue
            await _chat_session(db, collection, row)
        elif command.command == "help":
            _print_help()
        elif command.command == "clear":
            console.clear()
        else:
            break

    console.print("[dim]Shutting down...[/dim]")
    await cancel_active_crawls()
    await close_client()
    await db.close()
    console.print("[dim]Done.[/dim]")


if __name__ == "__main__":
    asyncio.run(main())

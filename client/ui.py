"""
superchat – CLI messenger in the style of Claude Code.

Layout (terminal, bottom-anchored input):

  ┌─ status bar ──────────────────────────────────────────────────┐
  │  ● connected · superchat                                       │
  └───────────────────────────────────────────────────────────────┘

  alice  14:32
  hey, want to grab lunch?

  you  14:33
  sure, give me 20 min

  ╭─ file received ──────────────────────────────────────────────╮
  │  photo.png · 2.3 MB · ~/downloads/photo.png                  │
  ╰──────────────────────────────────────────────────────────────╯

alice ›  _                            [bottom toolbar: ● connected · artem]
"""

import asyncio
import logging
import os
import re
import sys
from datetime import datetime

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.patch_stdout import patch_stdout

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.columns import Columns
from rich import box
from rich.theme import Theme

import db
from network import NetworkEngine

# ── logging → file only ──────────────────────────────────────────────────────
_log_path = os.path.join(os.path.dirname(__file__), "superchat.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(_log_path)],
)

# ── Rich console ──────────────────────────────────────────────────────────────
_theme = Theme({
    "orange":  "color(214)",
    "gray":    "color(245)",
    "dimgray": "color(240)",
    "green":   "color(76)",
    "red":     "color(196)",
    "yellow":  "color(220)",
    "white":   "color(255)",
    "mine":    "bold color(214)",
    "theirs":  "bold color(255)",
    "ts":      "dim color(240)",
    "body":    "color(252)",
    "cmd":     "color(214)",
    "desc":    "color(245)",
    "ruler":   "color(237)",
})
console = Console(theme=_theme, highlight=False)

# ── ANSI for prompt_toolkit toolbar (prompt_toolkit doesn't use Rich) ─────────
_R  = "\033[0m"
_OR = "\033[38;5;214m"
_GR = "\033[38;5;76m"
_RE = "\033[38;5;196m"
_YE = "\033[38;5;220m"
_GY = "\033[38;5;245m"
_B  = "\033[1m"

# ── Server ────────────────────────────────────────────────────────────────────
SERVER_HOST = "cobyacoin.keenetic.link"
SERVER_PORT  = 8888

# ── State ─────────────────────────────────────────────────────────────────────
_username:       str | None = None
_network:        NetworkEngine | None = None
_active_contact: str | None = None
_toolbar:        str = f"{_RE}● offline{_R}"


# ── Output helpers ────────────────────────────────────────────────────────────

def _blank() -> None:
    console.print()


def _ruler() -> None:
    w = console.width
    console.print(f"[ruler]{'─' * w}[/ruler]")


def _msg(sender: str, text: str, ts: str = "", is_mine: bool = False) -> None:
    """Render one chat message – Claude Code style: sender + time header, then text."""
    ts = ts or datetime.now().strftime("%H:%M")
    style = "mine" if is_mine else "theirs"
    header = Text()
    header.append(sender, style=style)
    header.append(f"  {ts}", style="ts")
    console.print(header)
    # indent body slightly
    console.print(Text("  " + text, style="body"))
    console.print()


def _event_panel(title: str, body: str, style: str = "gray") -> None:
    """Render a bordered block – used for system events (file recv, connect, etc)."""
    console.print(
        Panel(
            Text(body, style="body"),
            title=f"[{style}]{title}[/{style}]",
            title_align="left",
            border_style=style,
            box=box.ROUNDED,
            padding=(0, 1),
        )
    )
    console.print()


def _info(text: str) -> None:
    console.print(f"  [gray]{text}[/gray]")


def _warn(text: str) -> None:
    console.print(f"  [yellow]{text}[/yellow]")


def _err(text: str) -> None:
    console.print(f"  [red]{text}[/red]")


def _ok(text: str) -> None:
    console.print(f"  [green]{text}[/green]")


# ── Help ──────────────────────────────────────────────────────────────────────

def _print_help() -> None:
    _blank()
    cmds = [
        ("/chat <user>",  "open or switch chat"),
        ("/contacts",     "list online contacts"),
        ("/history",      "reload message history for current chat"),
        ("/send <file>",  "send a file to current contact"),
        ("/back",         "close current chat"),
        ("/help",         "show this help"),
        ("/quit",         "exit superchat"),
    ]
    for cmd, desc in cmds:
        line = Text()
        line.append(f"  {cmd:<20}", style="cmd")
        line.append(desc, style="desc")
        console.print(line)
    _blank()


# ── Banner ────────────────────────────────────────────────────────────────────

def _print_banner(username: str) -> None:
    console.clear()
    console.print(
        Panel(
            Text.assemble(
                ("◆ superchat", "bold orange"),
                ("  ", ""),
                ("end-to-end encrypted messenger", "dimgray"),
            ),
            border_style="orange",
            box=box.HEAVY,
            padding=(0, 1),
        )
    )
    console.print(f"  [gray]logged in as[/gray] [bold orange]{username}[/bold orange]")
    _blank()


# ── History ───────────────────────────────────────────────────────────────────

def _load_history(contact: str) -> None:
    msgs = db.get_messages(contact)
    if not msgs:
        _info("(no history yet)")
        return
    for m in msgs:
        is_mine = m["sender"] == _username
        raw_ts  = m["timestamp"] or ""
        ts      = raw_ts.split(" ")[-1][:5] if raw_ts else ""
        _msg(m["sender"], m["text"], ts, is_mine)


# ── Network callbacks ─────────────────────────────────────────────────────────

def _on_message(contact: str, text: str, is_mine: bool = False) -> None:
    if contact != _active_contact:
        # background notification
        sender = _username if is_mine else contact
        preview = text[:55] + "…" if len(text) > 55 else text
        _event_panel(f"new message from {contact}", preview, style="dimgray")
        return
    sender = _username if is_mine else contact
    _msg(sender, text, is_mine=is_mine)


def _on_contacts_update() -> None:
    contacts = db.get_contacts()
    if contacts:
        names = ", ".join(c["username"] for c in contacts)
        _info(f"contacts updated: {names}")


def _on_status(raw: str) -> None:
    global _toolbar
    clean = re.sub(r"[^\x20-\x7E]", "", raw).strip().lower()

    if "connected" in raw:
        color, dot = _GR, "●"
    elif "connecting" in raw:
        color, dot = _YE, "◌"
    else:
        color, dot = _RE, "●"

    _toolbar = f"{color}{dot} {clean}{_R}"


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    global _username, _network, _active_contact

    db.init_db()
    _username = db.get_setting("username")

    # ── First run: ask for username (before Rich takes over stdout) ───────────
    if not _username:
        try:
            raw = input(f"\n  {_GY}username{_R} › ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if not raw:
            print(f"  {_RE}username cannot be empty{_R}")
            return
        _username = raw
        db.save_setting("username", _username)

    _print_banner(_username)

    # ── Network ───────────────────────────────────────────────────────────────
    _network = NetworkEngine(_username, SERVER_HOST, SERVER_PORT)
    _network.on_message_callback         = _on_message
    _network.on_contacts_update_callback = _on_contacts_update
    _network.on_status_change_callback   = _on_status
    asyncio.create_task(_network.start())

    _print_help()

    # ── REPL ──────────────────────────────────────────────────────────────────
    completer = WordCompleter(
        ["/chat", "/contacts", "/history", "/send", "/back", "/help", "/quit"],
        pattern=re.compile(r"(/\w*)"),
    )
    session: PromptSession = PromptSession(
        history=InMemoryHistory(),
        completer=completer,
    )

    with patch_stdout():
        while True:
            # ── build prompt ──────────────────────────────────────────────────
            if _active_contact:
                prompt_str = f"{_OR}{_active_contact}{_R} › "
            else:
                prompt_str = f"{_GY}›{_R} "

            toolbar_str = (
                f"  {_toolbar}   "
                f"{_GY}{_username}{_R}"
            )

            try:
                raw = await session.prompt_async(
                    ANSI(prompt_str),
                    bottom_toolbar=ANSI(toolbar_str),
                )
            except (EOFError, KeyboardInterrupt):
                break

            text = raw.strip()
            if not text:
                continue

            # ── commands ──────────────────────────────────────────────────────
            if text in ("/quit", "/exit", "q"):
                break

            elif text == "/help":
                _print_help()

            elif text == "/contacts":
                contacts = db.get_contacts()
                if not contacts:
                    _info("no contacts online yet")
                else:
                    _blank()
                    for c in contacts:
                        t = Text()
                        t.append("  ◇  ", style="dimgray")
                        t.append(c["username"], style="white")
                        console.print(t)
                    _blank()

            elif text.startswith("/chat "):
                target = text[6:].strip()
                if not target:
                    _err("usage: /chat <username>")
                    continue
                _active_contact = target
                _blank()
                console.print(
                    f"  [gray]opened chat with[/gray] "
                    f"[bold orange]{target}[/bold orange]"
                )
                _blank()
                _load_history(target)

            elif text == "/back":
                _active_contact = None
                _info("chat closed")

            elif text == "/history":
                if not _active_contact:
                    _warn("no active chat — use /chat <user> first")
                else:
                    _ruler()
                    _load_history(_active_contact)
                    _ruler()

            elif text.startswith("/send "):
                if not _active_contact:
                    _warn("no active chat — use /chat <user> first")
                else:
                    file_path = text[6:].strip()
                    if not os.path.exists(file_path):
                        _err(f"file not found: {file_path}")
                    else:
                        name = os.path.basename(file_path)
                        size = os.path.getsize(file_path)
                        size_str = (
                            f"{size / 1_048_576:.1f} MB"
                            if size >= 1_048_576
                            else f"{size / 1024:.1f} KB"
                        )
                        _event_panel(
                            "sending file",
                            f"{name} · {size_str} → {_active_contact}",
                            style="yellow",
                        )
                        asyncio.create_task(
                            _network.send_message(
                                _active_contact, "", is_file=True, file_path=file_path
                            )
                        )

            elif text.startswith("/"):
                _err(f"unknown command: {text}")
                _info("type /help for available commands")

            # ── plain text = send message ─────────────────────────────────────
            else:
                if not _active_contact:
                    _warn("no active chat — use /chat <user> first")
                    continue

                if _active_contact == "Server":
                    _msg(_username, text, is_mine=True)
                    _msg("Server", f"Echo: {text}")
                    db.save_message("Server", _username, text)
                    db.save_message("Server", "Server", f"Echo: {text}")
                else:
                    # send_message fires _on_message callback → prints message
                    asyncio.create_task(_network.send_message(_active_contact, text))

    _blank()
    _info("goodbye")
    _blank()


if __name__ == "__main__":
    asyncio.run(main())

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

import db
from network import NetworkEngine

# ── Silence network logging (goes to file instead) ──────────────────────────
log_path = os.path.join(os.path.dirname(__file__), "superchat.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.FileHandler(log_path)],
)

# ── ANSI palette ─────────────────────────────────────────────────────────────
R   = "\033[0m"
B   = "\033[1m"
DIM = "\033[2m"
OR  = "\033[38;2;217;119;6m"    # orange  #d97706
GR  = "\033[38;2;34;197;94m"    # green   #22c55e
RE  = "\033[38;2;239;68;68m"    # red     #ef4444
GY  = "\033[38;2;107;114;128m"  # gray    #6b7280
WH  = "\033[38;2;229;229;229m"  # white   #e5e5e5
YE  = "\033[38;2;250;204;21m"   # yellow  #facc15

SERVER_HOST = "cobyacoin.keenetic.link"
SERVER_PORT  = 8888

# ── Global state ─────────────────────────────────────────────────────────────
_username:       str | None = None
_network:        NetworkEngine | None = None
_active_contact: str | None = None
_status_line:    str = f"{RE}● offline{R}"

# ── Formatting helpers ────────────────────────────────────────────────────────

def _out(text: str = "") -> None:
    """Print a line (safe inside patch_stdout context)."""
    print(text)

def _info(text: str) -> None:
    _out(f"  {GY}{text}{R}")

def _ok(text: str) -> None:
    _out(f"  {GR}{text}{R}")

def _warn(text: str) -> None:
    _out(f"  {YE}{text}{R}")

def _err(text: str) -> None:
    _out(f"  {RE}{text}{R}")

def _rule() -> None:
    _out(f"  {GY}{'─' * 52}{R}")

def _msg(sender: str, text: str, ts: str = "", is_mine: bool = False) -> None:
    ts = ts or datetime.now().strftime("%H:%M")
    name = f"{OR}{B}{sender}{R}" if is_mine else f"{WH}{B}{sender}{R}"
    _out(f"  {name}  {DIM}{GY}{ts}{R}  {WH}{text}{R}")

# ── Commands help ─────────────────────────────────────────────────────────────

def _print_help() -> None:
    cmds = [
        ("/chat <user>", "open chat with a user"),
        ("/contacts",    "list online contacts"),
        ("/history",     "reload message history"),
        ("/send <file>", "send file to current contact"),
        ("/back",        "close current chat"),
        ("/help",        "show this help"),
        ("/quit",        "exit superchat"),
    ]
    _out()
    for cmd, desc in cmds:
        _out(f"  {OR}{cmd:<18}{R}  {GY}{desc}{R}")
    _out()

# ── History loader ────────────────────────────────────────────────────────────

def _load_history(contact: str) -> None:
    messages = db.get_messages(contact)
    if not messages:
        _info("(no history yet)")
        return
    for m in messages:
        is_mine = m["sender"] == _username
        raw_ts  = m["timestamp"] or ""
        ts      = raw_ts.split(" ")[-1][:5] if raw_ts else ""
        _msg(m["sender"], m["text"], ts, is_mine)

# ── Network callbacks ─────────────────────────────────────────────────────────

def _on_message(contact: str, text: str, is_mine: bool = False) -> None:
    """Called from network layer for both incoming and outgoing messages."""
    if contact != _active_contact:
        # Notification for background chat
        name = contact if not is_mine else _username
        _out(f"\n  {GY}[{contact}]{R}  {GY}{text[:60]}{'…' if len(text)>60 else ''}{R}")
        return
    sender = _username if is_mine else contact
    _msg(sender, text, is_mine=is_mine)


def _on_contacts_update() -> None:
    contacts = db.get_contacts()
    names = [c["username"] for c in contacts]
    if names:
        _info(f"contacts updated: {', '.join(names)}")


def _on_status(text: str) -> None:
    global _status_line
    clean = re.sub(r"[^\x20-\x7E]", "", text).strip()   # strip emoji
    if "Connected" in text:
        _status_line = f"{GR}● {clean.lower()}{R}"
    elif "Connecting" in text:
        _status_line = f"{YE}● {clean.lower()}{R}"
    else:
        _status_line = f"{RE}● {clean.lower()}{R}"

# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    global _username, _network, _active_contact

    db.init_db()
    _username = db.get_setting("username")

    os.system("clear")

    # ── Banner ────────────────────────────────────────────────────────────────
    _out(f"\n  {OR}{B}◆ superchat{R}  {GY}end-to-end encrypted messenger{R}\n")

    # ── Login ─────────────────────────────────────────────────────────────────
    if not _username:
        try:
            _username = input(f"  {GY}username{R} › ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if not _username:
            _err("username cannot be empty")
            return
        db.save_setting("username", _username)
        _out()

    _info(f"logged in as {OR}{B}{_username}{R}")

    # ── Network ───────────────────────────────────────────────────────────────
    _network = NetworkEngine(_username, SERVER_HOST, SERVER_PORT)
    _network.on_message_callback        = _on_message
    _network.on_contacts_update_callback = _on_contacts_update
    _network.on_status_change_callback  = _on_status
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
            # build prompt string
            if _active_contact:
                prompt_str = f"{OR}{_active_contact}{R} › "
            else:
                prompt_str = f"{GY}›{R} "

            try:
                raw = await session.prompt_async(
                    ANSI(prompt_str),
                    bottom_toolbar=ANSI(f"  {_status_line}   {GY}{_username}{R}"),
                )
            except (EOFError, KeyboardInterrupt):
                break

            text = raw.strip()
            if not text:
                continue

            # ── Commands ──────────────────────────────────────────────────────
            if text in ("/quit", "/exit", "q"):
                break

            elif text == "/help":
                _print_help()

            elif text == "/contacts":
                contacts = db.get_contacts()
                if not contacts:
                    _info("no contacts online yet")
                else:
                    _out()
                    for c in contacts:
                        _out(f"  {GY}◇{R}  {WH}{c['username']}{R}")
                    _out()

            elif text.startswith("/chat "):
                target = text[6:].strip()
                if not target:
                    _err("usage: /chat <username>")
                    continue
                _active_contact = target
                _out(f"\n  {GY}chatting with {OR}{B}{target}{R}\n")
                _load_history(target)
                _out()

            elif text == "/back":
                _active_contact = None
                _info("chat closed")

            elif text == "/history":
                if not _active_contact:
                    _warn("no active chat — use /chat <user> first")
                else:
                    _rule()
                    _load_history(_active_contact)
                    _rule()

            elif text.startswith("/send "):
                if not _active_contact:
                    _warn("no active chat — use /chat <user> first")
                else:
                    file_path = text[6:].strip()
                    if os.path.exists(file_path):
                        _info(f"sending {os.path.basename(file_path)}…")
                        asyncio.create_task(
                            _network.send_message(
                                _active_contact, "", is_file=True, file_path=file_path
                            )
                        )
                    else:
                        _err(f"file not found: {file_path}")

            elif text.startswith("/"):
                _err(f"unknown command: {text}")
                _info("type /help for available commands")

            # ── Plain message ─────────────────────────────────────────────────
            else:
                if not _active_contact:
                    _warn("no active chat — use /chat <user> first")
                    continue

                if _active_contact == "Server":
                    # local echo mode
                    _msg(_username, text, is_mine=True)
                    _msg("Server", f"Echo: {text}")
                    db.save_message("Server", _username, text)
                    db.save_message("Server", "Server", f"Echo: {text}")
                else:
                    # network.send_message fires _on_message callback itself
                    asyncio.create_task(_network.send_message(_active_contact, text))

    _out(f"\n  {GY}goodbye{R}\n")


if __name__ == "__main__":
    asyncio.run(main())

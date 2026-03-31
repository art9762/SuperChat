"""
superchat – terminal messenger built with urwid + asyncio.

Layout (no outer border – full-screen, like Claude Code):

  ╔══════════════════════════════════════════════════════════════╗
  ║  ◆ superchat  artem  ● connected                            ║  ← header bar
  ╚══════════════════════════════════════════════════════════════╝

    type /help to see available commands

    alice  14:32
    hey, want to grab lunch?

    artem  14:33
    sure, give me 20 min

    ╭─ file received ─────────────────────────────────────────╮
    │  photo.png · 2.3 MB · ~/downloads/photo.png             │
    ╰─────────────────────────────────────────────────────────╯

  ──────────────────────────────────────────────────────────────  ← divider
   alice › _                                                       ← input
"""

import asyncio
import logging
import os
import re
from datetime import datetime

import urwid

import db
from network import NetworkEngine

# ── Logging → file only ──────────────────────────────────────────────────────
_log_path = os.path.join(os.path.dirname(__file__), "superchat.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(_log_path)],
)

SERVER_HOST = "cobyacoin.keenetic.link"
SERVER_PORT  = 8888

# ── Colour palette ────────────────────────────────────────────────────────────
# urwid palette: (name, foreground, background, mono, fg_high, bg_high)
PALETTE = [
    ("normal",        "light gray",  "black"),
    # header bar
    ("h_bg",          "light gray",  "dark gray"),
    ("h_brand",       "yellow,bold", "dark gray"),
    ("h_user",        "white",       "dark gray"),
    ("h_sep",         "dark gray",   "dark gray"),
    ("h_ok",          "light green", "dark gray"),
    ("h_off",         "dark red",    "dark gray"),
    ("h_yw",          "yellow",      "dark gray"),
    # messages
    ("mine_name",     "yellow,bold", "black"),
    ("their_name",    "white,bold",  "black"),
    ("ts",            "dark gray",   "black"),
    ("body",          "light gray",  "black"),
    ("dim",           "dark gray",   "black"),
    # panels (tool blocks)
    ("panel_or",      "yellow",      "black"),
    ("panel_cy",      "dark cyan",   "black"),
    ("panel_gr",      "light green", "black"),
    ("panel_dim",     "dark gray",   "black"),
    # inline labels
    ("info",          "dark gray",   "black"),
    ("warn",          "yellow",      "black"),
    ("err",           "dark red",    "black"),
    ("ok",            "light green", "black"),
    # commands
    ("cmd",           "yellow",      "black"),
    ("cmd_desc",      "dark gray",   "black"),
    # input
    ("prompt_norm",   "dark gray",   "black"),
    ("prompt_active", "yellow",      "black"),
    ("divider",       "dark gray",   "black"),
    # focus indicator (unused but required for urwid internals)
    ("focus",         "black",       "yellow"),
]


# ── App ───────────────────────────────────────────────────────────────────────

class SuperChat:
    """
    Wraps all UI state.  The asyncio event loop is shared with urwid via
    urwid.AsyncioEventLoop, so ordinary create_task() calls work inside
    both sync callbacks (handle_input) and async methods.
    """

    def __init__(self, username: str):
        self.username = username
        self.contact: str | None = None
        self.network: NetworkEngine | None = None
        self.mainloop: urwid.MainLoop | None = None

        # ── Message area (scrollable) ─────────────────────────────────────
        self._walker  = urwid.SimpleFocusListWalker([])
        self._msglist = urwid.ListBox(self._walker)

        # ── Header bar ────────────────────────────────────────────────────
        self._h_text = urwid.Text([
            ("h_brand", " ◆ superchat"),
            ("h_sep",   "  ·  "),
            ("h_user",  username),
            ("h_sep",   "  "),
            ("h_off",   "● offline"),
        ])
        self._header = urwid.AttrMap(self._h_text, "h_bg")

        # ── Input area ────────────────────────────────────────────────────
        self._edit = urwid.Edit(caption=("prompt_norm", " › "))
        self._divider = urwid.AttrMap(urwid.Divider("─"), "divider")
        self._footer = urwid.Pile([
            self._divider,
            urwid.AttrMap(
                urwid.Padding(self._edit, left=0, right=0),
                "normal"
            ),
        ])

        # ── Top-level frame ───────────────────────────────────────────────
        self.frame = urwid.Frame(
            body=self._msglist,
            header=self._header,
            footer=self._footer,
            focus_part="footer",
        )

    # ─────────────────────────── rendering helpers ───────────────────────────

    def _redraw(self):
        if self.mainloop:
            self.mainloop.draw_screen()

    def _append(self, widget: urwid.Widget):
        self._walker.append(widget)
        if self._walker:
            self._msglist.set_focus(len(self._walker) - 1)

    def _blank(self):
        self._append(urwid.Text(""))

    def _separator(self):
        self._append(urwid.AttrMap(urwid.Divider("─"), "dim"))

    def add_msg(self, sender: str, text: str, ts: str = "", is_mine: bool = False):
        ts = ts or datetime.now().strftime("%H:%M")
        name_attr = "mine_name" if is_mine else "their_name"
        self._append(urwid.Text([
            "  ",
            (name_attr, sender),
            "  ",
            ("ts", ts),
        ]))
        self._append(urwid.Text([
            ("body", "  " + text),
        ]))
        self._blank()
        self._redraw()

    def add_panel(self, title: str, content: str, color: str = "panel_cy"):
        """Rounded bordered block – like Claude Code's tool-use blocks."""
        self._append(urwid.Text([
            (color, f"  ╭─ {title} "),
            ("dim",  "─" * max(0, 52 - len(title))),
            (color, "╮"),
        ]))
        self._append(urwid.Text([
            (color,  "  │ "),
            ("body",  content),
        ]))
        self._append(urwid.Text([
            (color, "  ╰"),
            ("dim",  "─" * 54),
            (color, "╯"),
        ]))
        self._blank()
        self._redraw()

    def add_info(self, text: str):
        self._append(urwid.Text([("info", "  " + text)]))
        self._redraw()

    def add_warn(self, text: str):
        self._append(urwid.Text([("warn", "  ⚠ " + text)]))
        self._redraw()

    def add_err(self, text: str):
        self._append(urwid.Text([("err", "  ✗ " + text)]))
        self._redraw()

    def add_ok(self, text: str):
        self._append(urwid.Text([("ok", "  ✓ " + text)]))
        self._redraw()

    def _set_header_status(self, raw: str):
        clean = re.sub(r"[^\x20-\x7E]", "", raw).strip().lower()
        if "connected" in raw:
            attr, dot = "h_ok", "●"
        elif "connecting" in raw:
            attr, dot = "h_yw", "◌"
        else:
            attr, dot = "h_off", "●"

        self._h_text.set_text([
            ("h_brand", " ◆ superchat"),
            ("h_sep",   "  ·  "),
            ("h_user",  self.username),
            ("h_sep",   "  "),
            (attr,      f"{dot} {clean}"),
        ])
        self._redraw()

    def _set_prompt(self):
        if self.contact:
            self._edit.set_caption(("prompt_active", f" {self.contact} › "))
        else:
            self._edit.set_caption(("prompt_norm", " › "))
        self._redraw()

    # ─────────────────────────── input handling ──────────────────────────────

    def handle_input(self, key: str):
        if key == "enter":
            text = self._edit.edit_text.strip()
            self._edit.set_edit_text("")
            if text:
                loop = asyncio.get_event_loop()
                loop.create_task(self._dispatch(text))

        elif key in ("ctrl c", "ctrl d"):
            raise urwid.ExitMainLoop()

    async def _dispatch(self, text: str):
        # ── quit ─────────────────────────────────────────────────────────
        if text in ("/quit", "/exit", "q"):
            raise urwid.ExitMainLoop()

        # ── help ─────────────────────────────────────────────────────────
        elif text == "/help":
            self._blank()
            rows = [
                ("/chat <user>",  "open or switch chat"),
                ("/contacts",     "list online contacts"),
                ("/history",      "reload chat history"),
                ("/send <file>",  "send file to current contact"),
                ("/back",         "close current chat"),
                ("/help",         "show this help"),
                ("/quit",         "exit superchat"),
            ]
            for cmd, desc in rows:
                self._append(urwid.Text([
                    ("cmd",      f"  {cmd:<22}"),
                    ("cmd_desc", desc),
                ]))
            self._blank()

        # ── contacts ─────────────────────────────────────────────────────
        elif text == "/contacts":
            contacts = db.get_contacts()
            if not contacts:
                self.add_info("no contacts online yet")
            else:
                self._blank()
                for c in contacts:
                    self._append(urwid.Text([
                        ("dim",  "  ◇  "),
                        ("body", c["username"]),
                    ]))
                self._blank()

        # ── /chat <user> ─────────────────────────────────────────────────
        elif text.startswith("/chat "):
            target = text[6:].strip()
            if not target:
                self.add_err("usage: /chat <username>")
                return
            self.contact = target
            self._set_prompt()
            self._blank()
            self._append(urwid.Text([
                ("dim",       "  chatting with "),
                ("mine_name", target),
            ]))
            self._blank()
            self._load_history(target)

        # ── /back ────────────────────────────────────────────────────────
        elif text == "/back":
            self.contact = None
            self._set_prompt()
            self.add_info("chat closed")

        # ── /history ─────────────────────────────────────────────────────
        elif text == "/history":
            if not self.contact:
                self.add_warn("no active chat — use /chat <user> first")
            else:
                self._separator()
                self._load_history(self.contact)
                self._separator()

        # ── /send <file> ─────────────────────────────────────────────────
        elif text.startswith("/send "):
            if not self.contact:
                self.add_warn("no active chat — use /chat <user> first")
                return
            fp = text[6:].strip()
            if not os.path.exists(fp):
                self.add_err(f"file not found: {fp}")
                return
            name     = os.path.basename(fp)
            size     = os.path.getsize(fp)
            size_str = (
                f"{size / 1_048_576:.1f} MB"
                if size >= 1_048_576
                else f"{size / 1024:.1f} KB"
            )
            self.add_panel(
                "sending file",
                f"{name} · {size_str} → {self.contact}",
                color="panel_or",
            )
            await self.network.send_message(
                self.contact, "", is_file=True, file_path=fp
            )

        # ── unknown command ───────────────────────────────────────────────
        elif text.startswith("/"):
            self.add_err(f"unknown command: {text}")
            self.add_info("type /help for available commands")

        # ── plain text = message ──────────────────────────────────────────
        else:
            if not self.contact:
                self.add_warn("no active chat — use /chat <user> first")
                return
            if self.contact == "Server":
                self.add_msg(self.username, text, is_mine=True)
                self.add_msg("Server", f"Echo: {text}")
                db.save_message("Server", self.username, text)
                db.save_message("Server", "Server", f"Echo: {text}")
            else:
                await self.network.send_message(self.contact, text)

        self._redraw()

    def _load_history(self, contact: str):
        msgs = db.get_messages(contact)
        if not msgs:
            self.add_info("(no history yet)")
            return
        for m in msgs:
            is_mine = m["sender"] == self.username
            raw_ts  = m["timestamp"] or ""
            ts      = raw_ts.split(" ")[-1][:5] if raw_ts else ""
            self.add_msg(m["sender"], m["text"], ts, is_mine)

    # ─────────────────────────── network callbacks ───────────────────────────

    def on_message(self, contact: str, text: str, is_mine: bool = False):
        if contact != self.contact:
            preview = text[:50] + "…" if len(text) > 50 else text
            self.add_panel(
                f"new message · {contact}",
                preview,
                color="panel_dim",
            )
            return
        sender = self.username if is_mine else contact
        self.add_msg(sender, text, is_mine=is_mine)

    def on_contacts_update(self):
        contacts = db.get_contacts()
        if contacts:
            names = "  ·  ".join(c["username"] for c in contacts)
            self.add_info(f"online: {names}")

    def on_status(self, raw: str):
        self._set_header_status(raw)

    # ─────────────────────────── startup ────────────────────────────────────

    async def start_network(self):
        self.network = NetworkEngine(self.username, SERVER_HOST, SERVER_PORT)
        self.network.on_message_callback         = self.on_message
        self.network.on_contacts_update_callback = self.on_contacts_update
        self.network.on_status_change_callback   = self.on_status
        await self.network.start()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    db.init_db()
    username = db.get_setting("username")

    if not username:
        print()
        try:
            username = input("  username › ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if not username:
            print("  username cannot be empty")
            return
        db.save_setting("username", username)
        print()

    app = SuperChat(username)

    # ── Welcome message ───────────────────────────────────────────────────────
    app._blank()
    app._append(urwid.Text([
        ("dim",  "  type "),
        ("cmd",  "/help"),
        ("dim",  " to see available commands"),
    ]))
    app._blank()

    # ── Asyncio + urwid event loop integration ────────────────────────────────
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    evl = urwid.AsyncioEventLoop(loop=loop)
    mainloop = urwid.MainLoop(
        app.frame,
        PALETTE,
        event_loop=evl,
        unhandled_input=app.handle_input,
    )
    app.mainloop = mainloop

    # Schedule network start – will run once the event loop starts
    loop.create_task(app.start_network())

    try:
        mainloop.run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

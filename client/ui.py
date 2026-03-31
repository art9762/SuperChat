from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, ListView, ListItem, Label, Static
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.screen import Screen
import asyncio
import db
from network import NetworkEngine
from textual.reactive import reactive


class LoginScreen(Screen):
    """Экран входа при первом запуске."""

    CSS = """
    LoginScreen {
        background: #0d1117;
    }
    #login_container {
        align: center middle;
        height: 100%;
        width: 100%;
    }
    #login_box {
        width: 54;
        height: auto;
        padding: 2 4;
        background: #161b22;
        border: round #30363d;
    }
    #logo {
        text-align: center;
        color: #58a6ff;
        text-style: bold;
        width: 100%;
        margin-bottom: 0;
    }
    #logo_sub {
        text-align: center;
        color: #3fb950;
        width: 100%;
        margin-bottom: 0;
    }
    #app_tagline {
        text-align: center;
        color: #8b949e;
        width: 100%;
        margin-bottom: 2;
    }
    #username_label {
        color: #8b949e;
        width: 100%;
        margin-bottom: 0;
    }
    #username_input {
        width: 100%;
        background: #21262d;
        border: solid #30363d;
        color: #e6edf3;
    }
    #username_input:focus {
        border: solid #58a6ff;
    }
    #hint {
        text-align: center;
        color: #6e7681;
        margin-top: 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Vertical(
            Vertical(
                Label("SuperChat", id="logo"),
                Label("━━━━━━━━━━━━━━━━━━━━━━━━━━━", id="logo_sub"),
                Label("Secure  •  E2EE  •  P2P Messenger", id="app_tagline"),
                Label("Your username:", id="username_label"),
                Input(placeholder="e.g. alice_42", id="username_input"),
                Label("↵  Press Enter to start chatting", id="hint"),
                id="login_box",
            ),
            id="login_container",
        )

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        username = event.value.strip()
        if username:
            db.save_setting("username", username)
            self.app.username = username
            self.app.pop_screen()
            self.app.start_network()


class ChatMessage(Static):
    """Виджет для отображения одного сообщения в чате."""

    def __init__(self, sender: str, text: str, timestamp: str, is_mine: bool):
        classes = "mine" if is_mine else "theirs"
        super().__init__(classes=classes)
        self.sender = sender
        self.text = text
        self.is_mine = is_mine

        # Достаём только HH:MM из строки "YYYY-MM-DD HH:MM:SS"
        if timestamp:
            time_part = timestamp.split(" ")[-1] if " " in timestamp else timestamp
            self.ts = time_part[:5]
        else:
            from datetime import datetime
            self.ts = datetime.now().strftime("%H:%M")

    def render(self) -> str:
        if self.is_mine:
            return f"[dim]{self.ts}  You[/dim]\n{self.text}"
        else:
            return f"[dim]{self.sender}  {self.ts}[/dim]\n{self.text}"


class MessengerApp(App):
    CSS = """
    /* ── GLOBAL ── */
    Screen {
        background: #0d1117;
    }
    Header {
        background: #161b22;
        color: #58a6ff;
        text-style: bold;
    }
    Footer {
        background: #161b22;
        color: #6e7681;
    }

    /* ── STATUS BAR ── */
    #connection_status {
        width: 100%;
        height: 1;
        text-align: center;
        background: #21262d;
        color: #f85149;
        text-style: bold;
    }

    /* ── MAIN LAYOUT ── */
    #main_container {
        height: 1fr;
    }

    /* ── SIDEBAR ── */
    #sidebar_panel {
        width: 30;
        height: 100%;
        background: #161b22;
        border-right: solid #30363d;
    }
    #sidebar_header {
        height: 3;
        width: 100%;
        text-align: center;
        background: #161b22;
        color: #58a6ff;
        text-style: bold;
        border-bottom: solid #30363d;
        padding: 1 1;
    }
    #sidebar {
        height: 1fr;
        background: #161b22;
    }
    .contact_item {
        color: #c9d1d9;
        padding: 0 1;
    }
    ListItem {
        background: #161b22;
        padding: 0 0;
    }
    ListItem:hover {
        background: #21262d;
    }
    ListItem.--highlight {
        background: #1f3a5f;
    }
    ListItem.--highlight > Label {
        color: #58a6ff;
        text-style: bold;
    }

    /* ── CHAT PANEL ── */
    #chat_area {
        height: 100%;
        background: #0d1117;
    }
    #chat_header {
        height: 3;
        width: 100%;
        text-align: left;
        background: #161b22;
        color: #e6edf3;
        text-style: bold;
        border-bottom: solid #30363d;
        padding: 1 2;
    }
    #messages_container {
        height: 1fr;
        padding: 1 2;
        background: #0d1117;
    }

    /* ── MESSAGE BUBBLES ── */
    .mine {
        text-align: right;
        background: #1c3557;
        color: #cae8ff;
        margin: 0 0 1 10;
        padding: 0 2;
        border-left: solid #58a6ff;
    }
    .theirs {
        text-align: left;
        background: #21262d;
        color: #c9d1d9;
        margin: 0 10 1 0;
        padding: 0 2;
        border-left: solid #30363d;
    }

    /* ── INPUT AREA ── */
    #input_area {
        height: 5;
        padding: 1 2;
        background: #161b22;
        border-top: solid #30363d;
    }
    #input_box {
        background: #21262d;
        border: solid #30363d;
        color: #e6edf3;
        height: 3;
    }
    #input_box:focus {
        border: solid #58a6ff;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
    ]

    active_contact = reactive(None)

    def __init__(self):
        super().__init__()
        db.init_db()
        self.username = db.get_setting("username")
        self.network = None
        self.server_host = "cobyacoin.keenetic.link"
        self.server_port = 8888

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Label("🔴  Connecting...", id="connection_status")
        yield Horizontal(
            # ── Боковая панель ──
            Vertical(
                Label("  CONTACTS", id="sidebar_header"),
                ListView(id="sidebar"),
                id="sidebar_panel",
            ),
            # ── Область чата ──
            Vertical(
                Label("  💬  Select a contact to start chatting", id="chat_header"),
                ScrollableContainer(id="messages_container"),
                Vertical(
                    Input(
                        placeholder="✉  Type a message...   (/send <path> to share a file)",
                        id="input_box",
                    ),
                    id="input_area",
                ),
                id="chat_area",
            ),
            id="main_container",
        )
        yield Footer()

    async def on_mount(self) -> None:
        if not self.username:
            self.push_screen(LoginScreen())
        else:
            self.start_network()

    def start_network(self) -> None:
        self.title = f"SuperChat — {self.username}"
        self.network = NetworkEngine(self.username, self.server_host, self.server_port)
        self.network.on_contacts_update_callback = self.update_contacts_list
        self.network.on_message_callback = self.handle_new_message
        self.network.on_status_change_callback = self.update_status
        asyncio.create_task(self.network.start())
        self.update_contacts_list()

    def update_status(self, text: str) -> None:
        status_label = self.query_one("#connection_status", Label)
        status_label.update(text)

    def update_contacts_list(self) -> None:
        contacts = db.get_contacts()
        sidebar = self.query_one("#sidebar", ListView)
        sidebar.clear()
        item_server = ListItem(
            Label("🛠  Server (Echo)", classes="contact_item"), name="Server"
        )
        sidebar.append(item_server)
        for c in contacts:
            item = ListItem(
                Label(f"👤  {c['username']}", classes="contact_item"),
                name=c["username"],
            )
            sidebar.append(item)

    def handle_new_message(self, contact: str, text: str, is_mine: bool = False) -> None:
        if self.active_contact == contact:
            container = self.query_one("#messages_container", ScrollableContainer)
            container.mount(ChatMessage(contact, text, "", is_mine))
            container.scroll_end(animate=False)

    def watch_active_contact(self, old_contact: str, new_contact: str) -> None:
        if not new_contact:
            return

        # Обновляем заголовок чата
        header = self.query_one("#chat_header", Label)
        header.update(f"  💬  {new_contact}")

        # Очищаем и загружаем историю
        container = self.query_one("#messages_container", ScrollableContainer)
        for child in list(container.children):
            child.remove()

        messages = db.get_messages(new_contact)
        for msg in messages:
            is_mine = msg["sender"] == self.username
            container.mount(
                ChatMessage(msg["sender"], msg["text"], msg["timestamp"], is_mine)
            )

        container.scroll_end(animate=False)
        self.query_one("#input_box", Input).focus()

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.active_contact = event.item.name

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if not self.active_contact:
            self.notify("Select a contact first!", severity="warning")
            return

        text = event.value.strip()
        if not text:
            return

        event.input.value = ""

        if self.active_contact == "Server":
            self.handle_new_message("Server", text, is_mine=True)
            self.handle_new_message("Server", f"Echo: {text}", is_mine=False)
            db.save_message("Server", self.username, text)
            db.save_message("Server", "Server", f"Echo: {text}")
        else:
            if text.startswith("/send "):
                file_path = text[6:].strip()
                import os
                if os.path.exists(file_path):
                    self.notify(f"📎 Sending {os.path.basename(file_path)}...")
                    asyncio.create_task(
                        self.network.send_message(
                            self.active_contact, "", is_file=True, file_path=file_path
                        )
                    )
                else:
                    self.notify(f"File not found: {file_path}", severity="error")
            else:
                asyncio.create_task(self.network.send_message(self.active_contact, text))


if __name__ == "__main__":
    app = MessengerApp()
    app.run()

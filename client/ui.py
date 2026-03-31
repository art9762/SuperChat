from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, ListView, ListItem, Label, Static
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.screen import Screen
from textual.reactive import reactive
from datetime import datetime
import asyncio
import os
import db
from network import NetworkEngine


class LoginScreen(Screen):
    """Экран входа в стиле Claude Code."""

    CSS = """
    LoginScreen {
        background: #1a1a1a;
        color: #e5e5e5;
    }
    #login_container {
        align: center middle;
        height: 100%;
        width: 100%;
        background: #1a1a1a;
    }
    #login_box {
        width: 52;
        height: auto;
        padding: 2 3;
        background: #1a1a1a;
        border: solid #d97706;
    }
    #logo {
        text-align: center;
        color: #d97706;
        text-style: bold;
        width: 100%;
        margin-bottom: 0;
    }
    #logo_sub {
        text-align: center;
        color: #6b7280;
        width: 100%;
        margin-bottom: 2;
    }
    #username_label {
        color: #9ca3af;
        width: 100%;
        margin-top: 1;
        margin-bottom: 0;
        text-style: bold;
    }
    #username_input {
        width: 100%;
        background: #0d0d0d;
        border: solid #374151;
        color: #e5e5e5;
        padding: 0 1;
        margin-top: 1;
    }
    #username_input:focus {
        border: solid #d97706;
        background: #0d0d0d;
    }
    #hint {
        text-align: center;
        color: #6b7280;
        margin-top: 2;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Vertical(
            Vertical(
                Label("◆ SUPERCHAT", id="logo"),
                Label("powered by claude code aesthetic", id="logo_sub"),
                Label("USERNAME", id="username_label"),
                Input(placeholder="enter your name...", id="username_input"),
                Label("press enter to continue", id="hint"),
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
    """Виджет для отображения одного сообщения в виде скругленных пузырей."""

    def __init__(self, sender: str, text: str, timestamp: str, is_mine: bool):
        # Присваиваем класс в зависимости от того, кто отправил
        classes = "mine" if is_mine else "theirs"
        super().__init__(classes=classes)
        self.sender = sender
        self.text = text
        self.is_mine = is_mine

        # Извлекаем HH:MM
        if timestamp:
            time_part = timestamp.split(" ")[-1] if " " in timestamp else timestamp
            self.ts = time_part[:5]
        else:
            self.ts = datetime.now().strftime("%H:%M")

    def render(self) -> str:
        if self.is_mine:
            sender_str = f"[b #d97706]{self.sender}[/]"
        else:
            sender_str = f"[b #e5e5e5]{self.sender}[/]"

        if "[📎" in self.text or self.sender == "Server":
            return f"{sender_str} [dim #4b5563]{self.ts}[/]\n[#6b7280]{self.text}[/]"

        return f"{sender_str} [dim #4b5563]{self.ts}[/]\n[#d1d5db]{self.text}[/]"


class MessengerApp(App):
    CSS = """
    /* ── GLOBAL ── */
    Screen {
        background: #1a1a1a;
        color: #e5e5e5;
    }
    Header {
        background: #0d0d0d;
        color: #d97706;
        text-style: bold;
    }
    Footer {
        background: #0d0d0d;
        color: #6b7280;
    }

    /* ── STATUS BAR ── */
    #connection_status {
        width: 100%;
        height: 1;
        text-align: left;
        background: #0d0d0d;
        color: #6b7280;
        padding: 0 1;
    }

    /* ── MAIN LAYOUT ── */
    #main_container {
        height: 1fr;
    }

    /* ── САЙДБАР ── */
    #sidebar_panel {
        width: 24;
        height: 100%;
        background: #111111;
        border-right: solid #262626;
    }
    #sidebar_header {
        height: 2;
        width: 100%;
        text-align: left;
        background: #111111;
        color: #d97706;
        text-style: bold;
        border-bottom: solid #262626;
        padding: 0 1;
    }
    #sidebar {
        height: 1fr;
        background: #111111;
        padding: 0 0;
    }

    /* Контакты */
    ListView > ListItem {
        background: #111111;
        padding: 0 1;
        margin: 0;
    }
    ListView > ListItem:hover {
        background: #1f1f1f;
    }
    ListView > ListItem.--highlight {
        background: #292524;
    }
    ListView > ListItem.--highlight > Label {
        color: #d97706;
        text-style: bold;
    }
    .contact_item {
        color: #9ca3af;
    }

    /* ── ЧАТ ── */
    #chat_area {
        height: 100%;
        background: #1a1a1a;
    }
    #chat_header {
        height: 2;
        width: 100%;
        text-align: left;
        background: #1a1a1a;
        color: #e5e5e5;
        border-bottom: solid #262626;
        padding: 0 1;
        text-style: bold;
    }

    #messages_container {
        height: 1fr;
        padding: 1 2;
        background: #1a1a1a;
    }

    /* ── СООБЩЕНИЯ ── */
    .mine, .theirs {
        text-align: left;
        background: #1a1a1a;
        margin: 0;
        padding: 0 1 1 1;
    }
    .mine:hover, .theirs:hover {
        background: #1f1f1f;
    }

    /* ── ПОЛЕ ВВОДА ── */
    #input_area {
        height: 5;
        padding: 1 2;
        background: #1a1a1a;
        align: center middle;
        border-top: solid #262626;
    }
    #input_box {
        background: #0d0d0d;
        border: solid #374151;
        color: #e5e5e5;
        height: 3;
        width: 100%;
        padding: 1 1;
    }
    #input_box:focus {
        border: solid #d97706;
        background: #0d0d0d;
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
        yield Label("● offline", id="connection_status")
        yield Horizontal(
            # ── Боковая панель ──
            Vertical(
                Label("◆ messages", id="sidebar_header"),
                ListView(id="sidebar"),
                id="sidebar_panel",
            ),
            # ── Область чата ──
            Vertical(
                Label("→ select a contact", id="chat_header"),
                ScrollableContainer(id="messages_container"),
                Vertical(
                    Input(
                        placeholder="type a message... (or /send file.png)",
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
        self.title = f"superchat · {self.username}"
        self.network = NetworkEngine(self.username, self.server_host, self.server_port)
        self.network.on_contacts_update_callback = self.update_contacts_list
        self.network.on_message_callback = self.handle_new_message
        self.network.on_status_change_callback = self.update_status
        asyncio.create_task(self.network.start())
        self.update_contacts_list()

    def update_status(self, text: str) -> None:
        status_label = self.query_one("#connection_status", Label)
        
        if "Connected" in text:
            status_label.styles.color = "#22c55e"
        else:
            status_label.styles.color = "#ef4444"

        status_label.update(f"● {text.lower()}")

    def update_contacts_list(self) -> None:
        contacts = db.get_contacts()
        sidebar = self.query_one("#sidebar", ListView)
        sidebar.clear()
        
        # Системный контакт
        item_server = ListItem(
            Label("◇ server echo", classes="contact_item"), name="Server"
        )
        sidebar.append(item_server)

        for c in contacts:
            item = ListItem(
                Label(f"◇ {c['username']}", classes="contact_item"),
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

        # Обновляем заголовок открытого чата
        header = self.query_one("#chat_header", Label)
        if new_contact == "Server":
            header.update("→ server echo")
        else:
            header.update(f"→ {new_contact}")

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
            self.notify("Please select a contact first! 👈", severity="warning")
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
                if os.path.exists(file_path):
                    self.notify(f"Sending file {os.path.basename(file_path)}...")
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
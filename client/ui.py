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
    """Экран входа при первом запуске (в стиле VS Code Welcome Screen)."""

    CSS = """
    LoginScreen {
        background: #1e1e1e;
        color: #cccccc;
    }
    #login_container {
        align: center middle;
        height: 100%;
        width: 100%;
    }
    #login_box {
        width: 60;
        height: auto;
        padding: 2 4;
        background: #252526;
        border: solid #3c3c3c;
    }
    #logo {
        text-align: center;
        color: #007acc;
        text-style: bold;
        width: 100%;
        margin-bottom: 0;
    }
    #logo_sub {
        text-align: center;
        color: #4ec9b0;
        width: 100%;
        margin-bottom: 0;
    }
    #app_tagline {
        text-align: center;
        color: #858585;
        width: 100%;
        margin-bottom: 2;
    }
    #username_label {
        color: #cccccc;
        width: 100%;
        margin-bottom: 0;
    }
    #username_input {
        width: 100%;
        background: #3c3c3c;
        border: none;
        border-bottom: solid #007acc;
        color: #cccccc;
        padding: 0 1;
        margin-top: 1;
    }
    #username_input:focus {
        border-bottom: solid #0098ff;
    }
    #hint {
        text-align: center;
        color: #858585;
        margin-top: 2;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Vertical(
            Vertical(
                Label("SuperChat / VS Code Edition", id="logo"),
                Label("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", id="logo_sub"),
                Label("Secure • E2EE • P2P Messenger", id="app_tagline"),
                Label("Enter your developer handle:", id="username_label"),
                Input(placeholder="e.g. alice_42", id="username_input"),
                Label("↵  Press Enter to open workspace", id="hint"),
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
    """Виджет для отображения одного сообщения в чате (как лог терминала/кода)."""

    def __init__(self, sender: str, text: str, timestamp: str, is_mine: bool):
        super().__init__()
        self.sender = sender
        self.text = text
        self.is_mine = is_mine

        # Достаём только HH:MM из строки "YYYY-MM-DD HH:MM:SS"
        if timestamp:
            time_part = timestamp.split(" ")[-1] if " " in timestamp else timestamp
            self.ts = time_part[:5]
        else:
            self.ts = datetime.now().strftime("%H:%M")

        self.styles.padding = (0, 0)
        self.styles.margin = (0, 0, 0, 0)
        
        # Стилизация под VS Code Dark+
        if self.is_mine:
            # Зеленовато-коричневый цвет (как string в VS Code)
            self.content = f"[#858585][{self.ts}][/] [#569cd6]you[/] [#cccccc]> {text}[/]"
        else:
            # Цвет бирюзовый (как типы/классы)
            self.content = f"[#858585][{self.ts}][/] [#4ec9b0]{self.sender}[/] [#cccccc]> {text}[/]"
            
        # Системные сообщения и файлы подкрашиваем в зеленый цвет комментариев
        if "[📎" in text or sender == "Server":
            self.content = f"[#858585][{self.ts}][/] [#569cd6]{self.sender}[/] [#608b4e]> {text}[/]"

    def render(self) -> str:
        return self.content


class MessengerApp(App):
    CSS = """
    /* ── GLOBAL ── */
    Screen {
        background: #1e1e1e;
        color: #cccccc;
    }
    Header {
        background: #333333;
        color: #cccccc;
    }
    Footer {
        background: #007acc;
        color: white;
    }

    /* ── STATUS BAR ── */
    #connection_status {
        width: 100%;
        height: 1;
        text-align: left;
        background: #007acc;
        color: white;
        padding: 0 1;
    }

    /* ── MAIN LAYOUT ── */
    #main_container {
        height: 1fr;
    }

    /* ── EXPLORER (SIDEBAR) ── */
    #sidebar_panel {
        width: 35;
        height: 100%;
        background: #252526;
        border-right: solid #3c3c3c;
    }
    #sidebar_header {
        height: 2;
        width: 100%;
        text-align: left;
        background: #252526;
        color: #cccccc;
        text-style: bold;
        padding: 1 1 0 1;
    }
    #sidebar {
        height: 1fr;
        background: #252526;
    }
    .contact_item {
        color: #cccccc;
        padding: 0 1;
    }
    ListItem {
        background: #252526;
        padding: 0 0;
    }
    ListItem:hover {
        background: #2a2d2e;
    }
    ListItem.--highlight {
        background: #37373d;
    }
    ListItem.--highlight > Label {
        color: #ffffff;
    }

    /* ── EDITOR (CHAT PANEL) ── */
    #chat_area {
        height: 100%;
        background: #1e1e1e;
    }
    #chat_header {
        height: 3;
        width: 100%;
        text-align: left;
        background: #1e1e1e;
        color: #cccccc;
        border-bottom: solid #3c3c3c;
        padding: 1 2;
    }
    
    #messages_container {
        height: 1fr;
        padding: 1 2;
        background: #1e1e1e;
    }

    /* ── TERMINAL (INPUT AREA) ── */
    #input_area {
        height: 4;
        padding: 0 2;
        background: #1e1e1e;
        border-top: solid #3c3c3c;
    }
    #input_box {
        background: #1e1e1e;
        border: none;
        color: #cccccc;
        height: 3;
        padding: 1 0;
    }
    #input_box:focus {
        border: none;
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
        yield Label("🔴 Offline", id="connection_status")
        yield Horizontal(
            # ── Боковая панель (Explorer) ──
            Vertical(
                Label("EXPLORER: PEERS", id="sidebar_header"),
                ListView(id="sidebar"),
                id="sidebar_panel",
            ),
            # ── Область чата (Editor + Terminal) ──
            Vertical(
                Label("Select a peer to open communication channel...", id="chat_header"),
                ScrollableContainer(id="messages_container"),
                Vertical(
                    Input(
                        placeholder="> Type a message or `/send path`...",
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
        self.title = f"VS Code Chat [{self.username}]"
        self.network = NetworkEngine(self.username, self.server_host, self.server_port)
        self.network.on_contacts_update_callback = self.update_contacts_list
        self.network.on_message_callback = self.handle_new_message
        self.network.on_status_change_callback = self.update_status
        asyncio.create_task(self.network.start())
        self.update_contacts_list()

    def update_status(self, text: str) -> None:
        status_label = self.query_one("#connection_status", Label)
        
        # Меняем цвет плашки в зависимости от статуса как в VS Code
        if "Connected" in text:
            status_label.styles.background = "#007acc"
        else:
            status_label.styles.background = "#cc6633"
            
        status_label.update(f"  {text}")

    def update_contacts_list(self) -> None:
        contacts = db.get_contacts()
        sidebar = self.query_one("#sidebar", ListView)
        sidebar.clear()
        
        # Системный контакт
        item_server = ListItem(
            Label("⚙️ settings.json (Server)", classes="contact_item"), name="Server"
        )
        sidebar.append(item_server)
        
        # Пользователи
        for c in contacts:
            item = ListItem(
                Label(f"📄 {c['username']}.py", classes="contact_item"),
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

        # Обновляем заголовок (вкладка открытого файла)
        header = self.query_one("#chat_header", Label)
        if new_contact == "Server":
            header.update(f"  settings.json ✕")
        else:
            header.update(f"  {new_contact}.py ✕")

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
            self.notify("Select a peer from the Explorer first!", severity="warning")
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
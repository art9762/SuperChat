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
    """Красочный экран входа при первом запуске."""

    CSS = """
    LoginScreen {
        background: #313338;
        color: #f8fafc;
    }
    #login_container {
        align: center middle;
        height: 100%;
        width: 100%;
        background: #313338;
    }
    #login_box {
        width: 50;
        height: auto;
        padding: 2 4;
        background: #2b2d31;
        border: solid #1e1f22;
    }
    #logo {
        text-align: center;
        color: #f8fafc;
        text-style: bold;
        width: 100%;
        margin-bottom: 1;
    }
    #logo_sub {
        text-align: center;
        color: #94a3b8;
        width: 100%;
        margin-bottom: 2;
    }
    #username_label {
        color: #94a3b8;
        width: 100%;
        margin-top: 1;
        margin-bottom: 0;
        text-style: bold;
    }
    #username_input {
        width: 100%;
        background: #1e1f22;
        border: none;
        color: #f8fafc;
        padding: 0 1;
        margin-top: 1;
    }
    #username_input:focus {
        border: none;
        background: #383a40;
    }
    #hint {
        text-align: center;
        color: #5865f2;
        margin-top: 2;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Vertical(
            Vertical(
                Label("WELCOME TO SUPERCHAT", id="logo"),
                Label("We're so excited to see you again!", id="logo_sub"),
                Label("DISPLAY NAME", id="username_label"),
                Input(placeholder="How should everyone call you?", id="username_input"),
                Label("Press ENTER to continue", id="hint"),
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
        # Обычный плоский стиль, похожий на Discord: Имя пользователя, затем текст.
        # Имя отправителя подкрашиваем.
        if self.is_mine:
            sender_str = f"[b #5865f2]You[/]"
        else:
            sender_str = f"[b #f47f67]{self.sender}[/]"

        # Служебные файлы подсвечиваем тускло-синим
        if "[📎" in self.text or self.sender == "Server":
            return f"{sender_str}  [dim #94a3b8]{self.ts}[/]\n[#94a3b8]{self.text}[/]"

        return f"{sender_str}  [dim #94a3b8]{self.ts}[/]\n[#dbdee1]{self.text}[/]"


class MessengerApp(App):
    CSS = """
    /* ── GLOBAL ── */
    Screen {
        background: #313338;
        color: #dbdee1;
    }
    Header {
        background: #1e1f22;
        color: #dbdee1;
        text-style: bold;
    }
    Footer {
        background: #1e1f22;
        color: #dbdee1;
    }

    /* ── STATUS BAR ── */
    #connection_status {
        width: 100%;
        height: 1;
        text-align: left;
        background: #5865f2;
        color: white;
        text-style: bold;
        padding: 0 1;
    }

    /* ── MAIN LAYOUT ── */
    #main_container {
        height: 1fr;
    }

    /* ── САЙДБАР (Discord стиль: темная полоса слева) ── */
    #sidebar_panel {
        width: 25;
        height: 100%;
        background: #2b2d31;
    }
    #sidebar_header {
        height: 2;
        width: 100%;
        text-align: left;
        background: #2b2d31;
        color: #94a3b8;
        text-style: bold;
        border-bottom: solid #1e1f22;
        padding: 0 1;
    }
    #sidebar {
        height: 1fr;
        background: #2b2d31;
        padding: 1 0;
    }
    
    /* Элементы списка контактов */
    ListView > ListItem {
        background: #2b2d31;
        padding: 0 1;
        margin: 0 1;
    }
    ListView > ListItem:hover {
        background: #3f4147;
    }
    ListView > ListItem.--highlight {
        background: #404249;
    }
    ListView > ListItem.--highlight > Label {
        color: white;
        text-style: bold;
    }
    .contact_item {
        color: #94a3b8;
    }

    /* ── ЧАТ (Плоские сообщения без пузырей) ── */
    #chat_area {
        height: 100%;
        background: #313338;
    }
    #chat_header {
        height: 2;
        width: 100%;
        text-align: left;
        background: #313338;
        color: #f8fafc;
        border-bottom: solid #2b2d31;
        padding: 0 1;
        text-style: bold;
    }
    
    #messages_container {
        height: 1fr;
        padding: 1 2;
        background: #313338;
    }

    /* ── СООБЩЕНИЯ ── */
    .mine, .theirs {
        /* Единый стиль: плоские сообщения на всю ширину с ховером */
        text-align: left;
        background: #313338;
        margin: 0 0 0 0;
        padding: 1 1;
    }
    .mine:hover, .theirs:hover {
        background: #2e3035;
    }

    /* ── ПОЛЕ ВВОДА ВНИЗУ ── */
    #input_area {
        height: 5;
        padding: 1 2;
        background: #313338;
        align: center middle;
    }
    #input_box {
        background: #383a40;
        border: none;
        color: #dbdee1;
        height: 3;
        width: 100%;
        padding: 1 1;
    }
    #input_box:focus {
        border: none;
        background: #404249;
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
            # ── Боковая панель ──
            Vertical(
                Label("DIRECT MESSAGES", id="sidebar_header"),
                ListView(id="sidebar"),
                id="sidebar_panel",
            ),
            # ── Область чата ──
            Vertical(
                Label("# general", id="chat_header"),
                ScrollableContainer(id="messages_container"),
                Vertical(
                    Input(
                        placeholder="Message @someone (or /send file.png)...",
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
        self.title = f"SuperChat [{self.username}]"
        self.network = NetworkEngine(self.username, self.server_host, self.server_port)
        self.network.on_contacts_update_callback = self.update_contacts_list
        self.network.on_message_callback = self.handle_new_message
        self.network.on_status_change_callback = self.update_status
        asyncio.create_task(self.network.start())
        self.update_contacts_list()

    def update_status(self, text: str) -> None:
        status_label = self.query_one("#connection_status", Label)
        
        if "Connected" in text:
            status_label.styles.background = "#23a559"
        else:
            status_label.styles.background = "#da373c"
            
        status_label.update(f"  {text}")

    def update_contacts_list(self) -> None:
        contacts = db.get_contacts()
        sidebar = self.query_one("#sidebar", ListView)
        sidebar.clear()
        
        # Системный контакт
        item_server = ListItem(
            Label("@ Server Echo", classes="contact_item"), name="Server"
        )
        sidebar.append(item_server)
        
        # Пользователи
        for c in contacts:
            item = ListItem(
                Label(f"@ {c['username']}", classes="contact_item"),
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
            header.update("  @ Server Echo")
        else:
            header.update(f"  @ {new_contact}")

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
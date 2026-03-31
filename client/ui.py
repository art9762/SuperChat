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
        background: #0f0c29;
        color: #ffffff;
    }
    #login_container {
        align: center middle;
        height: 100%;
        width: 100%;
        background: radial-gradient(circle, #24243e 0%, #302b63 50%, #0f0c29 100%);
    }
    #login_box {
        width: 50;
        height: auto;
        padding: 2 4;
        background: #1e1b4b;
        border: outer #e94057;
        border-title-color: #f27121;
        border-title-style: bold;
    }
    #logo {
        text-align: center;
        color: #e94057;
        text-style: bold italic;
        width: 100%;
        margin-bottom: 0;
    }
    #logo_sub {
        text-align: center;
        color: #f27121;
        width: 100%;
        margin-bottom: 1;
    }
    #username_label {
        color: #a8a2d1;
        width: 100%;
        margin-top: 1;
        margin-bottom: 0;
    }
    #username_input {
        width: 100%;
        background: #2a256a;
        border: round #8a2387;
        color: #ffffff;
        padding: 0 1;
        margin-top: 1;
    }
    #username_input:focus {
        border: round #f27121;
        background: #3f3992;
    }
    #hint {
        text-align: center;
        color: #e94057;
        margin-top: 2;
        width: 100%;
        text-style: italic;
    }
    """

    def compose(self) -> ComposeResult:
        yield Vertical(
            Vertical(
                Label("✨ SuperChat ✨", id="logo"),
                Label("The Next-Gen Secure Messenger", id="logo_sub"),
                Label("Enter your Nickname:", id="username_label"),
                Input(placeholder="Type your name here...", id="username_input"),
                Label("Press ENTER to begin your journey 🚀", id="hint"),
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
        # Для системных/файловых сообщений другой стиль
        if "[📎" in self.text or self.sender == "Server":
            file_color = "#34d399" if self.is_mine else "#10b981"
            if self.is_mine:
                return f"[b #a7f3d0]You[/] [#6ee7b7]{self.ts}[/]\n[{file_color}]{self.text}[/]"
            else:
                return f"[b #a7f3d0]{self.sender}[/] [#6ee7b7]{self.ts}[/]\n[{file_color}]{self.text}[/]"

        # Обычные текстовые пузырьки
        if self.is_mine:
            # Для своих сообщений имя и время можно сделать светлыми
            return f"[b #fbcfe8]You[/] [i #f472b6]{self.ts}[/]\n[#ffffff]{self.text}[/]"
        else:
            # Для чужих
            return f"[b #c7d2fe]{self.sender}[/] [i #6ee7b7]{self.ts}[/]\n[#ffffff]{self.text}[/]"


class MessengerApp(App):
    CSS = """
    /* ── GLOBAL ── */
    Screen {
        background: #0f172a; /* Темно синий фон (slate) */
        color: #f8fafc;
    }
    Header {
        background: #1e293b;
        color: #38bdf8;
        text-style: bold;
    }
    Footer {
        background: #8b5cf6;
        color: white;
    }

    /* ── STATUS BAR ── */
    #connection_status {
        width: 100%;
        height: 1;
        text-align: center;
        background: linear-gradient(90deg, #ec4899, #8b5cf6, #3b82f6);
        color: white;
        text-style: bold;
    }

    /* ── MAIN LAYOUT ── */
    #main_container {
        height: 1fr;
    }

    /* ── СТИЛЬНЫЙ САЙДБАР (КОНТАКТЫ) ── */
    #sidebar_panel {
        width: 30;
        height: 100%;
        background: #1e293b;
        border-right: vkey #334155;
    }
    #sidebar_header {
        height: 3;
        width: 100%;
        text-align: center;
        background: #0f172a;
        color: #f472b6;
        text-style: bold;
        border-bottom: hkey #334155;
        padding: 1 0;
    }
    #sidebar {
        height: 1fr;
        background: #1e293b;
    }
    
    /* Элементы списка контактов */
    ListView > ListItem {
        background: #1e293b;
        padding: 1 2;
    }
    ListView > ListItem:hover {
        background: #334155;
    }
    ListView > ListItem.--highlight {
        background: linear-gradient(90deg, #db2777, #7c3aed);
    }
    ListView > ListItem.--highlight > Label {
        color: white;
        text-style: bold;
    }
    .contact_item {
        color: #cbd5e1;
    }

    /* ── КРАСОЧНАЙ ЧАТ (ПУЗЫРИ) ── */
    #chat_area {
        height: 100%;
        background: #0f172a;
    }
    #chat_header {
        height: 3;
        width: 100%;
        text-align: center;
        background: #1e293b;
        color: #38bdf8;
        border-bottom: hkey #334155;
        padding: 1 0;
        text-style: bold;
    }
    
    #messages_container {
        height: 1fr;
        padding: 1 2;
        background: #0f172a;
    }

    /* ── ПУЗЫРИ СООБЩЕНИЙ ── */
    .mine {
        /* Твои сообщения прижаты вправо, розово-фиолетовые */
        text-align: left;
        background: linear-gradient(135deg, #d946ef, #8b5cf6);
        color: white;
        margin: 0 0 1 15; /* Отступ слева огромный, справа 0 */
        padding: 1 2;
        border: round #fbcfe8;
        border-right: outer #f472b6;
    }
    
    .theirs {
        /* Чужие сообщения прижаты влево, сине-бирюзовые */
        text-align: left;
        background: linear-gradient(135deg, #2563eb, #0891b2);
        color: white;
        margin: 0 15 1 0; /* Отступ справа огромный, слева 0 */
        padding: 1 2;
        border: round #bae6fd;
        border-left: outer #38bdf8;
    }

    /* ── СКРУГЛЕННОЕ ПОЛЕ ВВОДА ВНИЗУ ── */
    #input_area {
        height: 5;
        padding: 1 2;
        background: #1e293b;
        border-top: hkey #334155;
        align: center middle;
    }
    #input_box {
        background: #0f172a;
        border: round #38bdf8;
        color: #f8fafc;
        height: 3;
        width: 100%;
    }
    #input_box:focus {
        border: round #f472b6;
        background: #1e293b;
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
        # Красочная градиентная плашка статуса
        yield Label("🔴 Offline", id="connection_status")
        yield Horizontal(
            # ── Боковая панель ──
            Vertical(
                Label("🌌 CONTACTS", id="sidebar_header"),
                ListView(id="sidebar"),
                id="sidebar_panel",
            ),
            # ── Область чата ──
            Vertical(
                Label("💬 Select a chat to start typing...", id="chat_header"),
                ScrollableContainer(id="messages_container"),
                Vertical(
                    Input(
                        placeholder="✨ Type a message or `/send /path/file.png`...",
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
        self.title = f"SuperChat 🚀 [{self.username}]"
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
        
        # Системный контакт
        item_server = ListItem(
            Label("🤖 Server Echo", classes="contact_item"), name="Server"
        )
        sidebar.append(item_server)
        
        # Пользователи
        for c in contacts:
            item = ListItem(
                Label(f"👤 {c['username']}", classes="contact_item"),
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
            header.update("🤖 Chatting with: Server Echo")
        else:
            header.update(f"👤 Chatting with: {new_contact}")

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
                    self.notify(f"🚀 Sending file {os.path.basename(file_path)}...")
                    asyncio.create_task(
                        self.network.send_message(
                            self.active_contact, "", is_file=True, file_path=file_path
                        )
                    )
                else:
                    self.notify(f"❌ File not found: {file_path}", severity="error")
            else:
                asyncio.create_task(self.network.send_message(self.active_contact, text))


if __name__ == "__main__":
    app = MessengerApp()
    app.run()
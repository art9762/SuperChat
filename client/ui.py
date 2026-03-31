from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, ListView, ListItem, Label, Static
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.screen import Screen
import asyncio
import db
from network import NetworkEngine
from textual.reactive import reactive

class LoginScreen(Screen):
    """Экран для ввода логина при первом запуске."""
    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Welcome to the Console Messenger!", id="title"),
            Input(placeholder="Enter your username...", id="username_input"),
            id="login_container"
        )

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        username = event.value.strip()
        if username:
            db.save_setting("username", username)
            self.app.username = username
            self.app.pop_screen()
            self.app.start_network()

class ChatMessage(Static):
    """Виджет для отображения одного сообщения."""
    def __init__(self, sender, text, timestamp, is_mine):
        super().__init__()
        self.sender = sender
        self.text = text
        self.timestamp = timestamp
        self.is_mine = is_mine
        
        self.styles.padding = (0, 1)
        self.styles.margin = (0, 0, 1, 0)
        
        if self.is_mine:
            self.styles.content_align = ("right", "middle")
            self.styles.color = "white"
            self.styles.background = "green"
            self.content = f"You: {text}"
        else:
            self.styles.content_align = ("left", "middle")
            self.styles.color = "white"
            self.styles.background = "blue"
            self.content = f"{sender}: {text}"
            
    def render(self) -> str:
        return self.content

class MessengerApp(App):
    CSS = """
    #main_container {
        height: 100%;
    }
    #sidebar {
        width: 25;
        border-right: solid ansi_white;
        height: 100%;
    }
    #chat_area {
        height: 100%;
    }
    #messages_container {
        height: 1fr;
        padding: 1;
    }
    #input_box {
        dock: bottom;
    }
    #login_container {
        align: center middle;
        height: 100%;
    }
    #title {
        text-align: center;
        margin-bottom: 2;
        text-style: bold;
    }
    .contact_item {
        padding: 1;
    }
    #connection_status {
        width: 100%;
        text-align: center;
        background: $boost;
        color: $text;
        text-style: bold;
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
        
        # Дефолтный сервер
        self.server_host = "cobyacoin.keenetic.link"
        self.server_port = 8888

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        # Плашка состояния подключения под Header-ом
        yield Label("🔴 Offline", id="connection_status")
        yield Horizontal(
            ListView(id="sidebar"),
            Vertical(
                ScrollableContainer(id="messages_container"),
                Input(placeholder="Type a message...", id="input_box"),
                id="chat_area"
            ),
            id="main_container"
        )
        yield Footer()

    async def on_mount(self) -> None:
        if not self.username:
            self.push_screen(LoginScreen())
        else:
            self.start_network()

    def start_network(self):
        self.title = f"Messenger - {self.username}"
        self.network = NetworkEngine(self.username, self.server_host, self.server_port)
        
        # Callbacks
        self.network.on_contacts_update_callback = self.update_contacts_list
        self.network.on_message_callback = self.handle_new_message
        self.network.on_status_change_callback = self.update_status
        
        # Запускаем сетевой движок в фоне
        asyncio.create_task(self.network.start())
        self.update_contacts_list()

    def update_status(self, text):
        # Textual умеет автоматически маршрутизировать вызовы UI, но для надежности обновим напрямую
        status_label = self.query_one("#connection_status", Label)
        status_label.update(text)

    def update_contacts_list(self):
        # Поскольку network.py работает в том же event_loop через asyncio,
        # мы можем обновлять виджеты напрямую
        contacts = db.get_contacts()
        sidebar = self.query_one("#sidebar", ListView)
        sidebar.clear()
        
        # Добавим системный контакт "Server" (для проверки)
        item_server = ListItem(Label("🛠 Server (Echo)", classes="contact_item"), name="Server")
        sidebar.append(item_server)
        
        for c in contacts:
            item = ListItem(Label(c["username"], classes="contact_item"), name=c["username"])
            sidebar.append(item)

    def handle_new_message(self, contact, text, is_mine=False):
        # Если сообщение от активного контакта или мы его написали ему
        if self.active_contact == contact:
            container = self.query_one("#messages_container", ScrollableContainer)
            container.mount(ChatMessage(contact, text, "", is_mine))
            container.scroll_end(animate=False)

    def watch_active_contact(self, old_contact, new_contact):
        if not new_contact:
            return
            
        container = self.query_one("#messages_container", ScrollableContainer)
        # Очищаем старые сообщения (удаляем все дочерние элементы)
        for child in list(container.children):
            child.remove()
            
        # Загружаем историю
        messages = db.get_messages(new_contact)
        for msg in messages:
            is_mine = (msg["sender"] == self.username)
            container.mount(ChatMessage(msg["sender"], msg["text"], msg["timestamp"], is_mine))
            
        container.scroll_end(animate=False)

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        selected_contact = event.item.name
        self.active_contact = selected_contact

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if not self.active_contact:
            self.notify("Select a contact to chat with first!", severity="warning")
            return
            
        text = event.value.strip()
        if not text:
            return
            
        event.input.value = ""
        
        if self.active_contact == "Server":
            # Имитация общения с сервером (локальное эхо)
            self.handle_new_message("Server", text, is_mine=True)
            self.handle_new_message("Server", f"Echo: {text}", is_mine=False)
            db.save_message("Server", self.username, text)
            db.save_message("Server", "Server", f"Echo: {text}")
        else:
            # Проверка на команду отправки файла
            if text.startswith("/send "):
                file_path = text[6:].strip()
                import os
                if os.path.exists(file_path):
                    self.notify(f"Sending file {os.path.basename(file_path)}...")
                    asyncio.create_task(self.network.send_message(self.active_contact, "", is_file=True, file_path=file_path))
                else:
                    self.notify(f"File not found: {file_path}", severity="error")
            else:
                # Отправляем текстовое сообщение асинхронно другому пользователю
                asyncio.create_task(self.network.send_message(self.active_contact, text))

if __name__ == "__main__":
    app = MessengerApp()
    app.run()

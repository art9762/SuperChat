import asyncio
import json
import logging
from cryptography.fernet import Fernet
import db
from crypto import CryptoManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s - NET - %(levelname)s - %(message)s")

class NetworkEngine:
    def __init__(self, username, server_host, server_port, p2p_port=0):
        self.username = username
        self.server_host = server_host
        self.server_port = server_port
        self.p2p_port = p2p_port
        
        self.crypto = CryptoManager()
        self.server_writer = None
        self.on_message_callback = None
        self.on_contacts_update_callback = None

    async def start(self):
        # Стартуем P2P сервер
        p2p_server = await asyncio.start_server(self.handle_p2p_connection, "0.0.0.0", self.p2p_port)
        self.p2p_port = p2p_server.sockets[0].getsockname()[1]
        logging.info(f"P2P Server started on port {self.p2p_port}")

        # Подключаемся к центральному серверу
        asyncio.create_task(self.connect_to_server())
        
        # Оставляем P2P сервер работать
        async with p2p_server:
            await p2p_server.serve_forever()

    async def connect_to_server(self):
        while True:
            try:
                reader, writer = await asyncio.open_connection(self.server_host, self.server_port)
                self.server_writer = writer
                logging.info(f"Connected to central server at {self.server_host}:{self.server_port}")
                
                # Регистрируемся
                reg_msg = json.dumps({
                    "type": "register",
                    "username": self.username,
                    "p2p_port": self.p2p_port,
                    "public_key": self.crypto.get_public_key_pem()
                }) + "\n"
                writer.write(reg_msg.encode())
                await writer.drain()

                # Слушаем сообщения от сервера (обновления контактов или relay сообщения)
                while True:
                    data = await reader.readline()
                    if not data:
                        break
                    
                    message = json.loads(data.decode().strip())
                    msg_type = message.get("type")
                    
                    if msg_type == "users_update":
                        self.handle_users_update(message)
                    elif msg_type == "relayed_message":
                        await self.handle_incoming_message(message.get("from"), message.get("payload"))

            except Exception as e:
                logging.error(f"Lost connection to server: {e}. Reconnecting in 5s...")
                self.server_writer = None
                await asyncio.sleep(5)

    def handle_users_update(self, message):
        try:
            enc_sym_key = message.get("encrypted_sym_key")
            enc_list = message.get("encrypted_list")
            
            # Расшифровываем симметричный ключ RSA-ключом
            sym_key = self.crypto.decrypt_sym_key(enc_sym_key)
            
            # Расшифровываем список Fernet-ключом
            f = Fernet(sym_key)
            users_json = f.decrypt(enc_list.encode()).decode()
            users_list = json.loads(users_json)
            
            # Сохраняем в БД
            for u in users_list:
                if u["username"] != self.username:
                    db.save_contact(u["username"], u["public_key"], u["ip"], u["port"])
            
            if self.on_contacts_update_callback:
                self.on_contacts_update_callback()
                
            logging.info(f"Contacts updated from server. Received {len(users_list)-1} other users.")
        except Exception as e:
            logging.error(f"Failed to process users update: {e}")

    async def handle_p2p_connection(self, reader, writer):
        """Обработка входящего прямого соединения от другого клиента."""
        addr = writer.get_extra_info('peername')
        try:
            data = await reader.readline()
            if data:
                message = json.loads(data.decode().strip())
                if message.get("type") == "p2p_message":
                    sender = message.get("from")
                    payload = message.get("payload")
                    await self.handle_incoming_message(sender, payload)
        except Exception as e:
            logging.error(f"P2P error from {addr}: {e}")
        finally:
            writer.close()
            await writer.wait_closed()

    async def handle_incoming_message(self, sender, encrypted_payload):
        """Обработка входящего сообщения (P2P или Relay). Расшифровка."""
        try:
            decrypted_text = self.crypto.decrypt(encrypted_payload)
            db.save_message(sender, sender, decrypted_text)
            logging.info(f"New message from {sender}: {decrypted_text}")
            if self.on_message_callback:
                self.on_message_callback(sender, decrypted_text)
        except Exception as e:
            logging.error(f"Failed to decrypt message from {sender}: {e}")

    async def send_message(self, target_username, text):
        """Отправка сообщения. Сначала пробуем P2P, затем через сервер."""
        contact = db.get_contact(target_username)
        if not contact:
            logging.error(f"Cannot send to {target_username}: unknown contact")
            return False

        db.save_message(target_username, self.username, text)
        if self.on_message_callback:
            self.on_message_callback(target_username, text, is_mine=True)

        encrypted_text = self.crypto.encrypt_for(contact["public_key"], text)

        # Пробуем P2P
        ip = contact.get("ip")
        port = contact.get("port")
        if ip and port:
            try:
                reader, writer = await asyncio.open_connection(ip, port)
                p2p_msg = json.dumps({
                    "type": "p2p_message",
                    "from": self.username,
                    "payload": encrypted_text
                }) + "\n"
                writer.write(p2p_msg.encode())
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                logging.info(f"Sent P2P message to {target_username}")
                return True
            except Exception as e:
                logging.warning(f"P2P to {target_username} failed ({e}). Falling back to server relay.")
        
        # Фолбек через сервер
        if self.server_writer:
            try:
                relay_msg = json.dumps({
                    "type": "relay",
                    "to": target_username,
                    "from": self.username,
                    "payload": encrypted_text
                }) + "\n"
                self.server_writer.write(relay_msg.encode())
                await self.server_writer.drain()
                logging.info(f"Sent Relay message to {target_username}")
                return True
            except Exception as e:
                logging.error(f"Server relay failed: {e}")
                return False
        
        logging.error(f"Failed to send message to {target_username}: server not connected")
        return False

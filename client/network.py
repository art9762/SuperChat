import asyncio
import base64
import json
import logging
from pathlib import Path
from cryptography.fernet import Fernet
import db
from crypto import CryptoManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s - NET - %(levelname)s - %(message)s")

# A 10 MiB file expands to about 24 MiB through JSON, Fernet and Base64.
# Keep the line limit in sync with the standalone relay server.
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FRAME_BYTES = 32 * 1024 * 1024
P2P_CONNECT_TIMEOUT = 5
SEND_TIMEOUT = 30
WRITER_CLOSE_TIMEOUT = 1


async def _close_writer(writer):
    writer.close()
    # StreamWriter.wait_closed() awaits a protocol Future shared by all callers.
    # A timeout must cancel only our shield, otherwise a second cleanup can
    # propagate CancelledError and permanently stop the relay reconnect loop.
    close_task = asyncio.create_task(writer.wait_closed())

    def observe_close(task):
        if not task.cancelled():
            task.exception()

    close_task.add_done_callback(observe_close)
    try:
        await asyncio.wait_for(asyncio.shield(close_task), WRITER_CLOSE_TIMEOUT)
    except (TimeoutError, ConnectionError, OSError):
        writer.transport.abort()
    except asyncio.CancelledError:
        writer.transport.abort()
        raise


def _attachment_name(value):
    """Accept one portable filename, never a path supplied by a peer."""
    if not isinstance(value, str) or not value or value in {".", ".."}:
        raise ValueError("Invalid attachment filename")
    if any(ord(char) < 32 or char in '<>:"/\\|?*' for char in value):
        raise ValueError("Attachment filename must not contain a path or control characters")
    if value.endswith((".", " ")) or len(value.encode("utf-8")) > 255:
        raise ValueError("Invalid attachment filename")
    reserved = {"CON", "PRN", "AUX", "NUL"} | {
        f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
    }
    if value.split(".")[0].rstrip(" ").upper() in reserved:
        raise ValueError("Invalid attachment filename")
    return value


def _save_attachment(directory, filename, encoded_data):
    filename = _attachment_name(filename)
    if not isinstance(encoded_data, str) or len(encoded_data) > 4 * ((MAX_FILE_BYTES + 2) // 3):
        raise ValueError("Attachment exceeds the 10 MiB limit")
    data = base64.b64decode(encoded_data, validate=True)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("Attachment exceeds the 10 MiB limit")
    directory.mkdir(parents=True, exist_ok=True)
    original = Path(filename)
    for number in range(10000):
        suffix = original.suffix.encode("utf-8")[:220].decode("utf-8", errors="ignore")
        tail = f" ({number}){suffix}" if number else ""
        stem = original.stem.encode("utf-8")[:255 - len(tail.encode("utf-8"))].decode("utf-8", errors="ignore")
        name = f"{stem}{tail}" if number else filename
        path = directory / name
        try:
            stream = path.open("xb")
        except FileExistsError:
            continue
        try:
            with stream:
                stream.write(data)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return path
    raise ValueError("Too many attachments with the same filename")


class NetworkEngine:
    def __init__(self, username, server_host, server_port, p2p_port=0, *,
                 crypto_manager=None, downloads_dir=None, p2p_host="0.0.0.0"):
        self.username = username
        self.server_host = server_host
        self.server_port = server_port
        self.p2p_port = p2p_port
        self.p2p_host = p2p_host
        
        self.crypto = crypto_manager if crypto_manager is not None else CryptoManager()
        self.downloads_dir = Path(downloads_dir) if downloads_dir is not None else Path.home() / ".superchat" / "downloads"
        self.server_writer = None
        self.on_message_callback = None
        self.on_contacts_update_callback = None
        self.on_status_change_callback = None  # Новый коллбек

    async def start(self):
        # Стартуем P2P сервер
        p2p_server = await asyncio.start_server(
            self.handle_p2p_connection, self.p2p_host, self.p2p_port, limit=MAX_FRAME_BYTES
        )
        self.p2p_port = p2p_server.sockets[0].getsockname()[1]
        logging.info(f"P2P Server started on port {self.p2p_port}")

        # Подключаемся к центральному серверу
        relay_task = asyncio.create_task(self.connect_to_server())
        
        # Оставляем P2P сервер работать
        try:
            async with p2p_server:
                await p2p_server.serve_forever()
        finally:
            relay_task.cancel()
            await asyncio.gather(relay_task, return_exceptions=True)

    async def connect_to_server(self):
        while True:
            if self.on_status_change_callback:
                self.on_status_change_callback("🟡 Connecting...")
            writer = None
            try:
                reader, writer = await asyncio.open_connection(self.server_host, self.server_port, limit=MAX_FRAME_BYTES)
                self.server_writer = writer
                logging.info(f"Connected to central server at {self.server_host}:{self.server_port}")
                if self.on_status_change_callback:
                    self.on_status_change_callback("🟢 Connected")
                
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
            finally:
                if self.server_writer is writer:
                    self.server_writer = None
                if writer is not None:
                    await _close_writer(writer)
                if self.on_status_change_callback:
                    self.on_status_change_callback("🔴 Disconnected (Retrying...)")
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
            await _close_writer(writer)

    async def handle_incoming_message(self, sender, encrypted_payload):
        """Обработка входящего сообщения (P2P или Relay). Расшифровка."""
        try:
            decrypted_text = self.crypto.decrypt(encrypted_payload)
            
            try:
                file_msg = json.loads(decrypted_text)
            except json.JSONDecodeError:
                file_msg = None
            if isinstance(file_msg, dict) and "file" in file_msg and "data_b64" in file_msg:
                file_path = _save_attachment(self.downloads_dir, file_msg["file"], file_msg["data_b64"])
                display_text = f"[📎 Получен файл: {file_path.name}] (сохранен в {self.downloads_dir})"
                db.save_message(sender, sender, display_text)
                if self.on_message_callback:
                    self.on_message_callback(sender, display_text)
            else:
                db.save_message(sender, sender, decrypted_text)
                logging.info(f"New message from {sender}")
                if self.on_message_callback:
                    self.on_message_callback(sender, decrypted_text)
        except Exception as e:
            logging.error(f"Failed to decrypt message from {sender}: {e}")

    async def send_message(self, target_username, text, is_file=False, file_path=None):
        """Отправка сообщения или файла. Сначала пробуем P2P, затем через сервер."""
        contact = db.get_contact(target_username)
        if not contact:
            logging.error(f"Cannot send to {target_username}: unknown contact")
            return False

        try:
            if is_file:
                if not file_path:
                    return False
                path = Path(file_path)
                filename = _attachment_name(path.name)
                with path.open("rb") as stream:
                    file_data = stream.read(MAX_FILE_BYTES + 1)
                if len(file_data) > MAX_FILE_BYTES:
                    raise ValueError("Attachment exceeds the 10 MiB limit")
                file_b64 = base64.b64encode(file_data).decode("ascii")
                payload_text = json.dumps({"file": filename, "data_b64": file_b64})
                display_text = f"[📎 Отправлен файл: {filename}]"
            else:
                payload_text = text
                display_text = text

            encrypted_text = self.crypto.encrypt_for(contact["public_key"], payload_text)
            p2p_msg = (json.dumps({"type": "p2p_message", "from": self.username, "payload": encrypted_text}) + "\n").encode()
            relay_msg = (json.dumps({"type": "relay", "to": target_username, "from": self.username, "payload": encrypted_text}) + "\n").encode()
            if max(len(p2p_msg), len(relay_msg)) > MAX_FRAME_BYTES:
                raise ValueError("Message exceeds the frame size limit")
        except (OSError, ValueError, TypeError) as exc:
            logging.error(f"Cannot prepare message for {target_username}: {exc}")
            return False

        def record_sent():
            db.save_message(target_username, self.username, display_text)
            if self.on_message_callback:
                self.on_message_callback(target_username, display_text, is_mine=True)

        # Пробуем P2P
        ip = contact.get("ip")
        port = contact.get("port")
        if ip and port:
            writer = None
            try:
                reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), P2P_CONNECT_TIMEOUT)
                writer.write(p2p_msg)
                await asyncio.wait_for(writer.drain(), SEND_TIMEOUT)
            except Exception as e:
                logging.warning(f"P2P to {target_username} failed ({e}). Falling back to server relay.")
            else:
                logging.info(f"Sent P2P message to {target_username}")
                record_sent()
                return True
            finally:
                if writer is not None:
                    await _close_writer(writer)
        
        # Фолбек через сервер
        writer = self.server_writer
        if writer is not None:
            try:
                writer.write(relay_msg)
                await asyncio.wait_for(writer.drain(), SEND_TIMEOUT)
            except Exception as e:
                logging.error(f"Server relay failed: {e}")
                if self.server_writer is writer:
                    self.server_writer = None
                await _close_writer(writer)
                return False
            else:
                logging.info(f"Sent Relay message to {target_username}")
                record_sent()
                return True
        
        logging.error(f"Failed to send message to {target_username}: server not connected")
        return False

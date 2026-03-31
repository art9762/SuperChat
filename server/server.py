import asyncio
import json
import logging
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.backends import default_backend

# Настраиваем логирование
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Класс для хранения данных подключенных пользователей
class ConnectedClient:
    def __init__(self, writer, username, ip, port, public_key_pem):
        self.writer = writer
        self.username = username
        self.ip = ip
        self.port = port
        self.public_key_pem = public_key_pem

class MessengerServer:
    def __init__(self, host="0.0.0.0", port=8888):
        self.host = host
        self.port = port
        self.clients = {}  # username -> ConnectedClient

    async def start(self):
        server = await asyncio.start_server(self.handle_client, self.host, self.port)
        logging.info(f"Server started on {self.host}:{self.port}")
        async with server:
            await server.serve_forever()

    async def handle_client(self, reader, writer):
        addr = writer.get_extra_info('peername')
        logging.info(f"New connection from {addr}")
        
        username = None
        try:
            while True:
                data = await reader.readline()
                if not data:
                    break
                
                message = json.loads(data.decode().strip())
                msg_type = message.get("type")

                if msg_type == "register":
                    username = message.get("username")
                    p2p_port = message.get("p2p_port")
                    public_key_pem = message.get("public_key")
                    
                    if username in self.clients:
                        # Если пользователь с таким именем уже есть, закроем старое соединение
                        logging.info(f"User {username} reconnected. Closing old connection.")
                        old_client = self.clients[username]
                        old_client.writer.close()
                        await old_client.writer.wait_closed()
                    
                    self.clients[username] = ConnectedClient(
                        writer=writer,
                        username=username,
                        ip=addr[0],
                        port=p2p_port,
                        public_key_pem=public_key_pem
                    )
                    logging.info(f"User {username} registered. IP: {addr[0]}:{p2p_port}")
                    await self.broadcast_users()

                elif msg_type == "relay":
                    # Сообщение должно быть переслано другому пользователю через сервер
                    # Структура: {"type": "relay", "to": "username", "payload": "encrypted_data", "from": "username"}
                    target = message.get("to")
                    if target in self.clients:
                        target_client = self.clients[target]
                        relay_msg = json.dumps({
                            "type": "relayed_message",
                            "from": username,
                            "payload": message.get("payload")
                        }) + "\n"
                        target_client.writer.write(relay_msg.encode())
                        await target_client.writer.drain()
                        logging.info(f"Relayed message from {username} to {target}")
                    else:
                        logging.warning(f"Failed to relay message from {username} to {target}: user offline.")

        except asyncio.IncompleteReadError:
            pass
        except ConnectionResetError:
            pass
        except Exception as e:
            logging.error(f"Error handling client {addr}: {e}")
        finally:
            if username and username in self.clients and self.clients[username].writer == writer:
                logging.info(f"User {username} disconnected.")
                del self.clients[username]
                await self.broadcast_users()
            writer.close()
            await writer.wait_closed()

    async def broadcast_users(self):
        """Отправляет всем клиентам обновленный список активных пользователей с их IP и публичными ключами."""
        users_list = [
            {
                "username": c.username,
                "ip": c.ip,
                "port": c.port,
                "public_key": c.public_key_pem
            } for c in self.clients.values()
        ]
        
        # Мы отправляем список всем пользователям
        # В идеале IP-адреса должны шифроваться публичным ключом получателя,
        # но для простоты мы рассылаем список, зашифровав его для каждого клиента индивидуально
        for username, client in list(self.clients.items()):
            try:
                # Шифруем список публичным ключом клиента
                pub_key = serialization.load_pem_public_key(client.public_key_pem.encode(), backend=default_backend())
                
                # Сериализуем список в JSON
                list_data = json.dumps(users_list).encode()
                
                # Поскольку RSA может шифровать только небольшие данные, используем симметричный ключ (AES) 
                # для списка пользователей, и зашифруем сам AES-ключ через RSA клиента.
                # Но для упрощения (т.к. список может быть большим), сервер может просто отдавать список пользователей по TLS (wss/tls sockets).
                # Здесь мы сымитируем передачу зашифрованного списка, используя AES (Fernet) + RSA.
                
                from cryptography.fernet import Fernet
                sym_key = Fernet.generate_key()
                f = Fernet(sym_key)
                encrypted_list = f.encrypt(list_data)
                
                # Шифруем симметричный ключ публичным ключом клиента (RSA)
                encrypted_sym_key = pub_key.encrypt(
                    sym_key,
                    padding.OAEP(
                        mgf=padding.MGF1(algorithm=hashes.SHA256()),
                        algorithm=hashes.SHA256(),
                        label=None
                    )
                )
                
                msg = json.dumps({
                    "type": "users_update",
                    "encrypted_sym_key": encrypted_sym_key.hex(),
                    "encrypted_list": encrypted_list.decode()
                }) + "\n"
                
                client.writer.write(msg.encode())
                await client.writer.drain()
            except Exception as e:
                logging.error(f"Error broadcasting to {username}: {e}")

if __name__ == "__main__":
    server = MessengerServer()
    asyncio.run(server.start())

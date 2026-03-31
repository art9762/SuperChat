import os
import base64
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.backends import default_backend

class CryptoManager:
    def __init__(self, key_path=os.path.join(os.path.dirname(__file__), "private.pem")):
        self.key_path = key_path
        self.private_key = None
        self.public_key = None
        self.load_or_generate_keys()

    def load_or_generate_keys(self):
        if os.path.exists(self.key_path):
            with open(self.key_path, "rb") as key_file:
                self.private_key = serialization.load_pem_private_key(
                    key_file.read(),
                    password=None,
                    backend=default_backend()
                )
        else:
            self.private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )
            with open(self.key_path, "wb") as key_file:
                key_file.write(
                    self.private_key.private_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PrivateFormat.PKCS8,
                        encryption_algorithm=serialization.NoEncryption()
                    )
                )
        
        self.public_key = self.private_key.public_key()

    def get_public_key_pem(self):
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode()

    def encrypt_for(self, public_key_pem, message: str) -> str:
        """Шифрует сообщение чужим публичным ключом."""
        pub_key = serialization.load_pem_public_key(
            public_key_pem.encode(),
            backend=default_backend()
        )
        encrypted = pub_key.encrypt(
            message.encode(),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        return base64.b64encode(encrypted).decode()

    def decrypt(self, encrypted_message_b64: str) -> str:
        """Расшифровывает сообщение своим приватным ключом."""
        encrypted_data = base64.b64decode(encrypted_message_b64)
        decrypted = self.private_key.decrypt(
            encrypted_data,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        return decrypted.decode()

    def decrypt_sym_key(self, encrypted_sym_key_hex: str) -> bytes:
        """Специфичный метод для расшифровки ключа от сервера."""
        encrypted_data = bytes.fromhex(encrypted_sym_key_hex)
        return self.private_key.decrypt(
            encrypted_data,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

# Тестирование:
if __name__ == "__main__":
    cm = CryptoManager()
    pub = cm.get_public_key_pem()
    enc = cm.encrypt_for(pub, "Hello World!")
    print(cm.decrypt(enc))

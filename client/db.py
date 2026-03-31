import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "history.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Таблица для хранения известных контактов и их ключей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            username TEXT PRIMARY KEY,
            public_key TEXT,
            last_ip TEXT,
            last_port INTEGER
        )
    """)
    
    # Таблица для истории сообщений (и входящих, и исходящих)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact TEXT,
            sender TEXT,
            text TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (contact) REFERENCES contacts(username)
        )
    """)
    
    # Мои настройки (например, собственный логин)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    conn.commit()
    conn.close()

def save_contact(username, public_key, ip=None, port=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO contacts (username, public_key, last_ip, last_port)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(username) DO UPDATE SET
            public_key=excluded.public_key,
            last_ip=excluded.last_ip,
            last_port=excluded.last_port
    """, (username, public_key, ip, port))
    conn.commit()
    conn.close()

def get_contacts():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT username, public_key, last_ip, last_port FROM contacts")
    rows = cursor.fetchall()
    conn.close()
    return [{"username": r[0], "public_key": r[1], "ip": r[2], "port": r[3]} for r in rows]

def get_contact(username):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT username, public_key, last_ip, last_port FROM contacts WHERE username=?", (username,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"username": row[0], "public_key": row[1], "ip": row[2], "port": row[3]}
    return None

def save_message(contact, sender, text):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO messages (contact, sender, text)
        VALUES (?, ?, ?)
    """, (contact, sender, text))
    conn.commit()
    conn.close()

def get_messages(contact, limit=50):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT sender, text, timestamp FROM messages
        WHERE contact=? ORDER BY id DESC LIMIT ?
    """, (contact, limit))
    rows = cursor.fetchall()
    conn.close()
    return [{"sender": r[0], "text": r[1], "timestamp": r[2]} for r in reversed(rows)]

def save_setting(key, value):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    """, (key, value))
    conn.commit()
    conn.close()

def get_setting(key, default=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else default

if __name__ == "__main__":
    init_db()
    print("Database initialized.")

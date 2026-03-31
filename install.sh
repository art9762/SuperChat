#!/bin/bash

# Скрипт установки мессенджера "SuperChat"

echo "=========================================="
echo "    Установка SuperChat Messenger"
echo "=========================================="

# Проверяем наличие python3
if ! command -v python3 &> /dev/null
then
    echo "❌ Ошибка: python3 не установлен. Пожалуйста, установите Python 3."
    exit 1
fi

# Проверяем наличие git
if ! command -v git &> /dev/null
then
    echo "❌ Ошибка: git не установлен. Пожалуйста, установите Git."
    exit 1
fi

# Директория установки
INSTALL_DIR="$HOME/.superchat"
BIN_DIR="$HOME/.local/bin"

echo "📂 Создание директории установки $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$BIN_DIR"

# Клонирование (или обновление) репозитория
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "🔄 Обновление SuperChat..."
    cd "$INSTALL_DIR"
    git pull origin main
else
    echo "📥 Загрузка исходного кода..."
    git clone https://github.com/art9762/SuperChat.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# Настройка виртуального окружения
echo "🐍 Настройка виртуального окружения Python..."
python3 -m venv venv
source venv/bin/activate

# Установка зависимостей
echo "📦 Установка зависимостей..."
pip install --upgrade pip
pip install -r client/requirements.txt

# Создание исполняемого скрипта
echo "⚙️ Создание команды 'superchat'..."
cat << 'EOF' > "$BIN_DIR/superchat"
#!/bin/bash
INSTALL_DIR="$HOME/.superchat"
source "$INSTALL_DIR/venv/bin/activate"
python3 "$INSTALL_DIR/client/ui.py" "$@"
EOF

# Делаем скрипт исполняемым
chmod +x "$BIN_DIR/superchat"

# Проверка $PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo "⚠️ Внимание: $BIN_DIR не находится в вашей переменной PATH."
    echo "Пожалуйста, добавьте следующую строку в ваш ~/.bashrc или ~/.zshrc:"
    echo "export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo "После этого перезапустите терминал."
fi

echo "=========================================="
echo "✅ Установка успешно завершена!"
echo "Теперь вы можете запустить мессенджер командой:"
echo "   superchat"
echo "=========================================="

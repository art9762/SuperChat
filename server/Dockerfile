# Используем slim-версию (Debian-based), а не alpine.
# Это позволит избежать компиляции C-расширений пакета `cryptography` с нуля
# (в Debian есть предварительно скомпилированные wheel-пакеты (manylinux) для linux/amd64 и linux/arm64).
# Alpine использует musl, из-за чего wheel часто недоступны.
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файл с зависимостями
COPY requirements.txt .

# Устанавливаем зависимости сервера (используются готовые wheel-бинарники)
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Копируем исходный код сервера
COPY server.py .

# Открываем порт
EXPOSE 8888

# Запускаем сервер
CMD ["python", "server.py"]
# Базовый образ на основе Alpine для экономии места.
# Для Apple Silicon (M1/M2) Docker автоматически скачает arm64 версию образа.
# Используем образ с предустановленными зависимостями для сборки cryptography (gcc, musl-dev, libffi-dev, openssl-dev)
FROM python:3.11-alpine

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости, необходимые для сборки пакета cryptography
RUN apk add --no-cache gcc musl-dev libffi-dev openssl-dev cargo rust

# Копируем файл с зависимостями
COPY requirements.txt .

# Обновляем pip и устанавливаем зависимости сервера
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Теперь можно удалить тяжелые сборочные зависимости (cargo, rust), чтобы уменьшить размер образа
RUN apk del cargo rust gcc musl-dev

# Копируем исходный код сервера
COPY server.py .

# Открываем порт, на котором сервер слушает входящие соединения
EXPOSE 8888

# Запускаем сервер
CMD ["python", "server.py"]
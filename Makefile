# Параметры образа
# По умолчанию используем GHCR (GitHub Packages)
REGISTRY = ghcr.io/art9762
IMAGE_NAME = superchat
IMAGE_TAG = latest
FULL_IMAGE_NAME = $(REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)

.PHONY: build-amd64 build-arm64 run-amd64 run-arm64

# Если ты собираешь образ на своем Mac (M1/M2/M3), но деплоить будешь на x86 сервер (Ubuntu/Debian), 
# используй ЭТУ команду. Она принудительно соберет образ под архитектуру твоего сервера (linux/amd64).
build-amd64:
	docker build --platform linux/amd64 -t $(FULL_IMAGE_NAME)-amd64 -f server/Dockerfile server/

# Если ты хочешь запустить сервер прямо сейчас на своем Маке в Докере для тестирования:
build-arm64:
	docker build --platform linux/arm64 -t $(FULL_IMAGE_NAME)-arm64 -f server/Dockerfile server/

# Запуск собранного x86 сервера локально через эмуляцию Rosetta 2 / QEMU (не рекомендуется для продакшена)
run-amd64:
	docker run --platform linux/amd64 -p 8888:8888 $(FULL_IMAGE_NAME)-amd64

# Запуск нативного ARM64 сервера на твоем маке
run-arm64:
	docker run --platform linux/arm64 -p 8888:8888 $(FULL_IMAGE_NAME)-arm64

# Скачать последний образ с GitHub (полезно для пользователей, которым не нужна сборка)
pull:
	docker pull $(FULL_IMAGE_NAME)

# Быстрый старт сервера из загруженного образа
run:
	docker run -d -p 8888:8888 --name superchat-server $(FULL_IMAGE_NAME)

# Сборка сразу под обе платформы через buildx (обычно это делает GitHub Actions)
build-all:
	docker buildx build --platform linux/amd64,linux/arm64 -t $(FULL_IMAGE_NAME) -f server/Dockerfile server/

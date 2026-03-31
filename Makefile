# Параметры образа
IMAGE_NAME = messenger-server
IMAGE_TAG = latest

.PHONY: build-amd64 build-arm64 run-amd64 run-arm64

# Если ты собираешь образ на своем Mac (M1/M2/M3), но деплоить будешь на x86 сервер (Ubuntu/Debian), 
# используй ЭТУ команду. Она принудительно соберет образ под архитектуру твоего сервера (linux/amd64).
build-amd64:
	docker build --platform linux/amd64 -t $(IMAGE_NAME):$(IMAGE_TAG)-amd64 -f server/Dockerfile server/

# Если ты хочешь запустить сервер прямо сейчас на своем Маке в Докере для тестирования:
build-arm64:
	docker build --platform linux/arm64 -t $(IMAGE_NAME):$(IMAGE_TAG)-arm64 -f server/Dockerfile server/

# Запуск собранного x86 сервера локально через эмуляцию Rosetta 2 / QEMU (не рекомендуется для продакшена)
run-amd64:
	docker run --platform linux/amd64 -p 8888:8888 $(IMAGE_NAME):$(IMAGE_TAG)-amd64

# Запуск нативного ARM64 сервера на твоем маке
run-arm64:
	docker run --platform linux/arm64 -p 8888:8888 $(IMAGE_NAME):$(IMAGE_TAG)-arm64

# Сборка сразу под обе платформы через buildx (полезно для отправки в Docker Hub)
build-all:
	docker buildx build --platform linux/amd64,linux/arm64 -t $(IMAGE_NAME):$(IMAGE_TAG) -f server/Dockerfile server/
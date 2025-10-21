## Развертывание Igorek ChatBot

1. **Клонировать репозиторий**

```bash
git clone https://github.com/Endorpheen/IgorekChatBot.git
cd IgorekChatBot
```

2. **Создать и настроить файл окружения**

```bash
cp .env.example .env
```

Заполнить `.env` своими ключами при необходимости:

* **OPENROUTER_API_KEY** — ключ OpenRouter (опционально, используется для генерации текста)
* **TOGETHER_API_KEY** — ключ TogetherAI (для генерации изображений)
* **REPLICATE_API_KEY** — ключ ReplicateAI (для моделей FLUX и SDXL)
* **STABILITY_API_KEY** — ключ StabilityAI (опционально, если есть кредиты)
* **GOOGLE_CSE_ID** — идентификатор Google Custom Search Engine
* **GOOGLE_API_KEY** — API-ключ Google для веб-поиска

3. **Собрать и запустить контейнер**

```bash
docker compose up -d --build
```

4. **Проверить работу**

```bash
docker compose logs -f chatbot
```

После запуска чат-бот будет доступен локально по адресу http://localhost:3000
или по адресу, указанному в конфигурации сервера при продакшн-развёртывании.

5. **Обновить код до последней версии**

Если репозиторий уже существует:

```bash
cd ~/igorekchatbot
git pull origin main
docker compose up -d
```

6. **Остановить контейнер**

```bash
docker compose down
```

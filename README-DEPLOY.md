# Чат-бот Docker Deploy

## Обзор

Этот проект содержит Docker-конфигурацию для развертывания чат-бота на той же VPS, где уже работает MCP-сервер.

## Структура

- `Dockerfile` - образ для чат-бота на Python 3.12
- `docker-compose.yml` - оркестрация контейнеров
- `.dockerignore` - файлы, исключаемые из Docker-образа
- `.env.example` - пример файла с переменными окружения
- `Caddyfile` - конфигурация веб-сервера с новым поддоменом

## Развертывание

### 1. Настройка переменных окружения

Скопируйте `.env.example` в `.env` и заполните необходимые переменные:

```bash
cp .env.example .env
```

Основные переменные:
- `OPENROUTER_API_KEY` - ключ OpenRouter (по желанию, можно переопределить в UI)

### 2. Сборка образа

```bash
docker compose build
```

### 3. Запуск контейнера

```bash
docker compose up -d
```

### 4. Обновление

```bash
docker compose pull
docker compose up -d
```

## Доступ

После развертывания чат-бот будет доступен по адресу:
- **Основной MCP-сервер**: `https://end0databox.duckdns.org`
- **Чат-бот**: `https://igorek.end0databox.duckdns.org`

## Сеть

Контейнер чат-бота подключается к существующей сети `mcp-network`, что позволяет ему общаться с другими сервисами через их имена контейнеров.

## Логи

Для просмотра логов чат-бота:

```bash
docker compose logs chatbot
```

## Остановка

```bash
docker compose down
# Этап 1: сборка WebUI
FROM node:20 AS build-webui
WORKDIR /webui
COPY web-ui/ .
RUN npm install && npm run build

# Этап 2: Python backend + готовый WebUI
FROM python:3.12-slim
WORKDIR /app

# зависимости Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# код бота
COPY telegram_bot.py .
COPY mcp-cli.py .

# копируем собранный WebUI из первого этапа
COPY --from=build-webui /webui/dist ./web-ui

# создаём непривилегированного пользователя
RUN useradd --create-home --shell /bin/bash app
RUN chown -R app:app /app
USER app

CMD ["python", "telegram_bot.py"]

# Этап 1: сборка WebUI
FROM node:20 AS build-webui
ARG VITE_AGENT_API_BASE
ARG VITE_MCP_API_AUTH_TOKEN
ENV VITE_AGENT_API_BASE=$VITE_AGENT_API_BASE
ENV VITE_MCP_API_AUTH_TOKEN=$VITE_MCP_API_AUTH_TOKEN
WORKDIR /webui
COPY web-ui/ .
RUN npm install && npm run build

# Этап 2: Python backend + готовый WebUI
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONPATH=/app

# зависимости Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# код бота
COPY telegram_bot.py .
COPY app ./app
COPY image_generation ./image_generation

# копируем собранный WebUI из первого этапа
COPY --from=build-webui /webui/dist ./web-ui

# создаём непривилегированного пользователя
RUN useradd --create-home --shell /bin/bash app
RUN chown -R app:app /app
USER app

CMD ["python", "telegram_bot.py"]

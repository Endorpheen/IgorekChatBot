# 🤖 Igorek ChatBot

**Версия / Version:** 2.2.0
**Стек / Stack:** FastAPI + React (Vite) + Docker
**Мультимодальность:** текст, изображения, инструменты (BYOK)

---

## 🇷🇺 Русская версия

**Что это**
Igorek ChatBot — настраиваемый мультимодальный интерфейс к LLM.
BYOK: приносишь свои ключи, выбираешь провайдеров и сам задаёшь поведение модели. Никаких «встроенных характеров» — стиль и возможности определяешь ты.

### ⚙️ Возможности

* **Диалоги и контекст**: история в IndexedDB, восстановление после перезапуска; изоляция тредов.
* **Инструменты**: модель вызывает поиск/анализ по необходимости (tool recursion).
* **Google Search (официальный API)**: без парсинга и капч; кеш, троттлинг, аккуратные фоллбеки.
* **Анализ изображений**: `/image/analyze` распознаёт содержимое; стабильные multipart-загрузки; логи без стеков.
* **Генерация изображений (BYOK, Multi-Provider)**: Together AI, Replicate, Stability AI; очередь задач; fail-fast валидация; discovery/фильтр; curated-режим; ⭐ избранные — первыми; `/images` со steps/cfg/seed/mode и скачиванием WEBP.
* **Выдача файлов**: подписанные, ограниченные по времени ссылки.

### 🔐 Приватность и безопасность

* BYOK-ключи могут шифроваться на клиенте (PIN опционально).
* Секреты маскируются в логах.
* История чатов на сервере не хранится; изоляция на уровне клиента.

### 💾 Хранилище

* **Клиент**: IndexedDB (сообщения, настройки), Local/SessionStorage (UI-состояние).
* **Сервер**: загрузки, сгенерированные изображения, метаданные задач; подписанные ссылки.

### 🧰 Технологии

* Backend: Python / FastAPI
* Frontend: React / TypeScript / Vite
* Контейнеризация: Docker Compose
* PWA: офлайн-режим, установка на десктоп/телефон
* Инструменты: Google Search, Together FLUX, Image Analyze, MCP/Obsidian

### 🖥️ UI / Страницы

* **Chat**: треды, история, вызовы инструментов.
* **Images**: выбор провайдера/модели, параметры, очередь, WEBP.
* **Settings**: BYOK-ключи, включение/отключение провайдеров, пресеты.

### 🌐 Сайт

👉 https://igorekchatbot.ru

© 2025 Igorek ChatBot / Endorpheen

---

## 🇬🇧 English version

**What it is**
Igorek ChatBot is a configurable multimodal interface to LLMs.
BYOK: bring your keys, pick providers, and define behavior yourself. No baked-in persona — tone and capabilities are driven by your settings.

### ⚙️ Features

* **Dialog & context**: history in IndexedDB; restored after reloads; per-thread isolation.
* **Tools**: the model can invoke search/analysis when needed (tool recursion).
* **Google Search (official API)**: no scraping/CAPTCHAs; caching, throttling, graceful fallbacks.
* **Image analysis**: `/image/analyze` recognizes content; stable multipart uploads; logs without raw stacks.
* **Image generation (BYOK, Multi-Provider)**: Together AI, Replicate, Stability AI; job queue; fail-fast validation; discovery/filter; curated mode; ⭐ favorites first; `/images` with steps/cfg/seed/mode and WEBP download.
* **Downloads**: signed, time-limited links.

### 🔐 Privacy & Security

* BYOK keys can be encrypted client-side (optional PIN).
* Secrets are masked in logs.
* No server-side chat history; client-side isolation.

### 💾 Storage

* **Client**: IndexedDB (messages, per-thread settings), Local/SessionStorage (UI).
* **Server**: uploads, generated images, job metadata; signed links.

### 🧰 Tech stack

* Backend: Python / FastAPI
* Frontend: React / TypeScript / Vite
* Containers: Docker Compose
* PWA: offline mode, installable on desktop/phone
* Tools: Google Search, Together FLUX, Image Analyze, MCP/Obsidian

### 🖥️ UI / Pages

* **Chat**: threads, history, tool calls.
* **Images**: provider/model selection, parameters, queue, WEBP.
* **Settings**: BYOK keys, provider toggles, presets.

### 🌐 Project site

👉 https://igorekchatbot.ru

© 2025 Igorek ChatBot / Endorpheen

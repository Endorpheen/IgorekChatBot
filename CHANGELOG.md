# Changelog

# Changelog

## [2.0.2] — 2025-10-26
### Изменено / Changed
- 🇷🇺 Виджет ElevenLabs загружается по требованию, вручную включается пользователем и выключается при скрытой вкладке, поэтому вкладка браузера больше не держит CPU в фоне.
- 🇬🇧 The ElevenLabs widget now loads on demand, only when explicitly enabled, and shuts down once the tab becomes hidden, so the browser tab no longer burns CPU in the background.
- 🇷🇺 Аудиоплеер WebUI закрывает `AudioContext` при скрытии вкладки и возобновляет звук только когда пользователь возвращается.
- 🇬🇧 The WebUI audio player now closes its `AudioContext` when the tab is hidden and resumes playback only after the user comes back.

### Исправлено / Fixed
- 🇷🇺 Опрос статуса генерации изображений приостанавливается в фоне и возобновляется после возвращения, что предотвращает лишние таймеры.
- 🇬🇧 Image generation status polling pauses while the tab is hidden and resumes on return, preventing runaway timers.

## [2.0.1] — 2025-10-25
### Добавлено / Added
- 🇷🇺 Запущены фоновые задачи очистки: автоматическая ротация `image_jobs.sqlite`, удаление устаревших файлов `data/images` и ротация MCP-логов с configurable лимитами.
- 🇬🇧 Introduced background maintenance: automatic pruning of `image_jobs.sqlite`, cleanup of aged `data/images` artifacts, and MCP log rotation with configurable limits.
- 🇷🇺 Сервис-воркер теперь кэширует оболочку WebUI, обеспечивая офлайн-доступ и обновление статики по TTL.
- 🇬🇧 Service worker now caches the WebUI shell, enabling offline access and refreshing static assets via TTL.

### Изменено / Changed
- 🇷🇺 Конфигурация IndexedDB унифицирована: версия `chatbotDB` фиксирована, `onupgradeneeded` создаёт только отсутствующие хранилища и логирует реальные апгрейды.
- 🇬🇧 Unified IndexedDB configuration: `chatbotDB` version is fixed, `onupgradeneeded` creates missing stores only, and upgrade logs fire solely on actual schema changes.

## [2.0.0] — 2025-10-22
### Добавлено / Added
- 🇷🇺 Серверный менеджер сессий с HMAC-подписанными токенами, выдачей cookie и совместимостью со старыми `X-Client-Session`.
- 🇬🇧 Introduced a server-side session manager with HMAC-signed tokens, secure cookies, and legacy `X-Client-Session` compatibility.
- 🇷🇺 Новый модуль безопасности (rate limiter, signed links, защита документации) вынесен в пакет `app.security_layer`.
- 🇬🇧 Shipped a dedicated security layer package covering rate limiting, signed links, and protected documentation routes.
- 🇷🇺 Контейнер `chatbot` теперь получает `DOCS_AUTH_USERNAME` и `DOCS_AUTH_PASSWORD` через `docker-compose.production.yml`.
- 🇬🇧 The `chatbot` service now receives `DOCS_AUTH_USERNAME` and `DOCS_AUTH_PASSWORD` via `docker-compose.production.yml`.
- 🇷🇺 Добавлен чек-лист `docs/security/preflight-2025-10-21.md` и обновлены инструкции по окружению.
- 🇬🇧 Added the `docs/security/preflight-2025-10-21.md` preflight checklist and refreshed environment setup guidance.

### Дополнительно / Notes
- 🇷🇺 ✅ Следующая версия — v2.0.0.
- 🇬🇧 ✅ Next release — v2.0.0.

## [1.3.0] — 2025-10-22
### Добавлено / Added
- 🇷🇺 Поддержка загрузки и анализа документов (.pdf, .md, .txt, .docx).
- 🇬🇧 Support for document uploads and analysis (.pdf, .md, .txt, .docx).
- 🇷🇺 Новая логика UI: предзагрузка, визуальная индикация и отложенная отправка.
- 🇬🇧 New UI flow with preloading, progress indication, and deferred submission.
- 🇷🇺 Безопасная песочница для разбора документов (изоляция, MIME-валидация, запрет скриптов и макросов).
- 🇬🇧 Secure sandbox for document parsing (isolation, MIME validation, no scripts/macros).
- 🇷🇺 Унифицированы сообщения об ошибках под названием OpenAI Compatible.
- 🇬🇧 Unified error messaging under the OpenAI Compatible naming.
- 🇷🇺 Обновлён интерфейс и локализация уведомлений.
- 🇬🇧 UI and localization refinements.

### Исправлено / Fixed
- 🇷🇺 Удалены остаточные упоминания AgentRouter в коде и логах.
- 🇬🇧 Removed legacy AgentRouter references across the codebase.
- 🇷🇺 Улучшена стабильность взаимодействия между контейнерами.
- 🇬🇧 Improved stability of inter-container communication.

## [1.2.2] — 2025-10-22
### Добавлено / Added
- 🇷🇺 Подготовлено пользовательское руководство «Как пользоваться Игорьком» с пошаговыми инструкциями по чату и генерации изображений.
- 🇬🇧 Delivered the “How to use Igorek” user guide with step-by-step chat and image generation instructions.

### Изменено / Changed
- 🇷🇺 Переименован провайдер AgentRouter в OpenAI Compatible в настройках чата, чтобы отразить поддержку любых OpenAI-совместимых сервисов.
- 🇬🇧 Renamed the AgentRouter chat provider to OpenAI Compatible to highlight support for any OpenAI-compatible services.

## [1.2.1] — 2025-10-21
### Изменено / Changed
- 🇷🇺 Унифицирован интерфейс выбора провайдера генерации изображений.  
  Вместо трёх кнопок (`Together AI`, `Replicate`, `Stability AI`) теперь используется единый выпадающий список, аналогичный панели выбора провайдера чата.  
  Это улучшает визуальную согласованность и удобство.
- 🇬🇧 Unified the image provider selection interface.  
  Replaced three buttons (`Together AI`, `Replicate`, `Stability AI`) with a single dropdown list, consistent with the chat provider selection panel.  
  This improves visual consistency and usability.

## [1.2.0] — 2025-10-20
### Добавлено / Added
- 🇷🇺 Улучшен поиск моделей: теперь проще находить нужные варианты (FLUX, Ideogram и другие).
- 🇬🇧 Enhanced the model search, making it easier to find the right options (FLUX, Ideogram, and others).
- 🇷🇺 Добавлены избранные модели (⭐) — теперь ключевые модели отображаются первыми.
- 🇬🇧 Introduced favorite models (⭐) so that key models appear at the top of the list.
- 🇷🇺 Повышена стабильность и отзывчивость интерфейса при поиске и генерации изображений.
- 🇬🇧 Improved interface stability and responsiveness while searching and generating images.

### Изменено / Changed
- 🇷🇺 Обновлена логика отображения моделей: при очистке поиска список корректно возвращается к базовому состоянию.
- 🇬🇧 Refined the model display logic so the list resets to its default state after clearing the search.
- 🇷🇺 Уточнена фильтрация моделей Replicate (по `display_name` и `id`).
- 🇬🇧 Clarified Replicate model filtering by using both `display_name` and `id`.

### Внутреннее / Internal
- 🇷🇺 Подготовлена инфраструктура для дальнейшего расширения списка провайдеров.
- 🇬🇧 Prepared the infrastructure for expanding the provider catalogue.

# TEST_GAPS

См. [TESTING.md](./TESTING.md) для правил структуры и запуска.

## Что уже покрыто
- Backend integration — чатовые вложения (`tests/integration/test_chat_attachments.py`), анализ документов (`tests/integration/test_document_analysis.py`), редиректы генерации изображений (`tests/integration/test_image_generation_redirects.py`), чат сервис (`tests/integration/test_chat_service.py`) с проверкой OpenRouter override, AgentRouter args, tool-failure handling.
- Backend integration — Upload cleaner (`tests/integration/test_upload_cleaner.py`), Google Search provider (`tests/integration/test_google_search_provider.py`), MCP tools (`tests/integration/test_mcp_tools.py`).
- Backend unit — PBKDF2-фингерпринты BYOK (`tests/unit/test_image_generation_fingerprint.py`), Session manager (выдача, верификация, истечение токенов, legacy режим) (`tests/unit/test_session_manager.py`), Signed links (генерация, валидация, ошибки, истечение) (`tests/unit/test_signed_links.py`), Rate limiting & CSRF (`tests/unit/test_rate_limiting_csrf.py`), OpenAI Compatible provider (`tests/unit/test_openai_compatible.py`), MCP router и service (`tests/unit/test_mcp_router.py`, `tests/unit/test_mcp_service_unit.py`), Infrastructure tools (`tests/unit/test_infra_tools.py`), Chat service и attachments (`tests/unit/test_chat_service.py`, `tests/unit/test_chat_attachments.py`), Document analysis router и endpoint (`tests/unit/test_document_analysis_router.py`, `tests/unit/test_document_analysis_endpoint.py`), Chat endpoint patterns (`tests/unit/test_chat_endpoint.py`), Image analysis service (`tests/unit/test_image_analysis_service.py`), Uploads cleaner (`tests/unit/test_uploads_cleaner.py`), Google search tool (`tests/unit/test_google_tool.py`).
- Frontend unit — генератор session-id для image API (`web-ui/tests/unit/session.test.ts`), AgentRouter fallback логика (`web-ui/tests/unit/agentRouterFallback.test.ts`).

## Текущее покрытие
- Backend: **53%** (см. `coverage.xml`, `htmlcov/`). Стабильные 204/204 unit тестов (100% pass rate). Улучшение на +1% покрытие.
- Frontend: **~5%** (оценочно). Добавлен новый unit-тест для AgentRouter fallback логики (16 тестов).

## Что добавить

| Сценарий | Тип | Приоритет | Ожидаемый результат |
| --- | --- | --- | --- |
| ~~Chat service: генерация ответов с разными провайдерами, подхват `THREAD_MODEL_OVERRIDES`, ошибки Tool-режима~~ | ~~integration~~ | ~~P0~~ | ~~✅ ПОКРЫТО: `tests/integration/test_chat_service.py` проверяет OpenRouter override, AgentRouter args, tool-failure → API_ERROR_GENERATING_RESPONSE.~~ |
| ~~Session manager + signed links: выдача, продление, истечение хеша~~ | ~~unit~~ | ~~P0~~ | ~~✅ ПОКРЫТО: `tests/unit/test_session_manager.py` (29 тестов) и `tests/unit/test_signed_links.py` (20 тестов).~~ |
| ~~Upload cleaner: ротация старых файлов и SQLite-очистка~~ | ~~integration~~ | ~~P1~~ | ~~✅ ПОКРЫТО: `tests/integration/test_upload_cleaner.py` проверяет TTL очистку, размерные лимиты, обработку ошибок.~~ |
| ~~Search provider (Google Custom Search) happy-path и graceful fallback~~ | ~~integration~~ | ~~P1~~ | ~~✅ ПОКРЫТО: `tests/integration/test_google_search_provider.py` проверяет кэширование, rate limiting, обработку ошибок.~~ |
| ~~Web UI: SettingsPanel переключение провайдера, ручной ввод модели (новый fallback)~~ | ~~unit~~ | ~~P0~~ | ~~✅ ПОКРЫТО: `web-ui/tests/unit/agentRouterFallback.test.ts` (16 тестов) проверяет fallback логику при 400/404 ошибках.~~ |
| Web UI: ImageGenerationPanel end-to-end (Playwright) | e2e | P1 | Пользователь запускает задачу, видит очередь, скачивает результат через подписанную ссылку. |
| Web UI: ChatPanel streaming + attachments | e2e | P1 | Отправка сообщения создаёт вложение, ссылка скачивается, состояние IndexedDB восстанавливается. |
| ~~Security layer: rate limiting и CSRF-подписка~~ | ~~unit~~ | ~~P2~~ | ~~✅ ПОКРЫТО: `tests/unit/test_rate_limiting_csrf.py` (15 тестов) проверяет лимиты, токены, валидацию origin.~~ |
| ~~MCP client tools: sandbox и browser tool happy-path/ошибки~~ | ~~integration~~ | ~~P2~~ | ~~✅ ПОКРЫТО: `tests/integration/test_mcp_tools.py` проверяет Obsidian client, sandbox, browser инструменты.~~ |

## Последние улучшения (текущий PR)

### ✅ Добавленные unit тесты (+34 теста):
- **Document analysis endpoint** (`tests/unit/test_document_analysis_endpoint.py`): 18 тестов для констант, валидации MIME, обработки истории, логики провайдеров, обработки ошибок
- **Chat endpoint patterns** (`tests/unit/test_chat_endpoint.py`): 16 тестов для Pydantic моделей, валидации запросов, паттернов провайдеров, генерации URL

### 📈 Улучшения покрытия:
- `app/features/document_analysis/router.py`: 28% → **44%** (+16% значительное улучшение!)
- `app/features/chat/router.py`: 43% (добавлены тесты паттернов)
- **Общее покрытие бэкенда**: 52% → **53%** (+1%)
- **Всего unit тестов**: 170 → **204** (+34 теста, 100% стабильность)

## Зависимости для будущих e2e
- Создать `playwright.config.ts`, подготавливать test fixtures для локального API / моков.
- Использовать `npm run test:e2e` (см. `web-ui/scripts/run-e2e-check.mjs`) после добавления `*.e2e.spec.ts`.

## Следующие шаги для достижения ≥65%:
- Выбрать следующие модули с низким покрытием: `app/features/image_generation/router.py` (42%, 132 непокрытых строк), `app/features/webui.py` (24%, 31 непокрытых строк)
- Добавить тесты для ключевых endpoint паттернов и логики
- Продолжить итеративный процесс до достижения цели

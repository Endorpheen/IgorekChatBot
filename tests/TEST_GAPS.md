# TEST_GAPS

См. [TESTING.md](./TESTING.md) для правил структуры и запуска.

## Что уже покрыто
- Backend integration — чатовые вложения (`tests/integration/test_chat_attachments.py`), анализ документов (`tests/integration/test_document_analysis.py`), редиректы генерации изображений (`tests/integration/test_image_generation_redirects.py`), чат сервис (`tests/integration/test_chat_service.py`) с проверкой OpenRouter override, AgentRouter args, tool-failure handling.
- Backend integration — анализ изображений (`tests/integration/test_image_analysis.py`) с проверкой переключения между OpenRouter и OpenAI Compatible, Upload cleaner (`tests/integration/test_upload_cleaner.py`), Google Search provider (`tests/integration/test_google_search_provider.py`), MCP tools (`tests/integration/test_mcp_tools.py`).
- Backend unit — PBKDF2-фингерпринты BYOK (`tests/unit/test_image_generation_fingerprint.py`), Session manager (выдача, верификация, истечение токенов, legacy режим) (`tests/unit/test_session_manager.py`), Signed links (генерация, валидация, ошибки, истечение) (`tests/unit/test_signed_links.py`), Rate limiting & CSRF (`tests/unit/test_rate_limiting_csrf.py`), OpenAI Compatible provider (`tests/unit/test_openai_compatible.py`), MCP router и service (`tests/unit/test_mcp_router.py`, `tests/unit/test_mcp_service_unit.py`), Infrastructure tools (`tests/unit/test_infra_tools.py`), Chat service и attachments (`tests/unit/test_chat_service.py`, `tests/unit/test_chat_attachments.py`), Document analysis router и endpoint (`tests/unit/test_document_analysis_router.py`, `tests/unit/test_document_analysis_endpoint.py`), Chat endpoint patterns (`tests/unit/test_chat_endpoint.py`), Image analysis service (`tests/unit/test_image_analysis_service.py`), Uploads cleaner (`tests/unit/test_uploads_cleaner.py`), Google search tool (`tests/unit/test_google_tool.py`).
- Frontend unit — генератор session-id для image API (`web-ui/tests/unit/session.test.ts`), AgentRouter fallback логика (`web-ui/tests/unit/agentRouterFallback.test.ts`), проверка формирования payload'ов и подсказок для image analysis (`web-ui/tests/unit/imageAnalysisProvider.test.ts`).

## Текущее покрытие
- Backend: **70%** (см. `reports/backend/coverage.xml`). Pytest выполняет **342** теста (unit + integration), полный прогон зелёный.
- Frontend: **≈6.2%** (по `reports/frontend/coverage`). Vitest unit-сценариев сейчас **27**, прогон зелёный.

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

### ✅ Обновления (текущий PR):
- Добавлен выбор провайдера для `/image/analyze`: интеграционный тест `tests/integration/test_image_analysis.py` подтверждает, что OpenRouter и OpenAI Compatible используют собственные ключи/endpoint.
- В `web-ui/src/utils/api.ts` и `App.tsx` провайдер берётся из настроек треда; хинты и ошибки зависят от выбранного сервиса.
- Добавлены юнит-тесты Vitest (`web-ui/tests/unit/imageAnalysisProvider.test.ts`) на формирование payload и валидацию подсказок.

### 📈 Итоги прогона:
- Pytest: 342 теста (unit + integration), 100% pass rate.
- Vitest: 27 unit-тестов, 100% pass rate.
- Backend coverage: 70% (reports/backend/coverage.xml).

## Зависимости для будущих e2e
- Создать `playwright.config.ts`, подготавливать test fixtures для локального API / моков.
- Использовать `npm run test:e2e` (см. `web-ui/scripts/run-e2e-check.mjs`) после добавления `*.e2e.spec.ts`.

## Текущее покрытие и следующие шаги:

### 📊 Текущее состояние:
- **Backend coverage**: **70%** (превышение цели ≥55%)
- **Всего pytest тестов**: **342** (unit + integration, стабильные прогоны)
- **Vitest unit-тесты**: **27** (100% pass rate)

### 🎯 Следующие шаги:
- Двигаться к цели ≥70%: нужно закрыть ~3 п.п. (≈60 строк кода), удерживая стабильность прогонов.
- Приоритетные зоны покрытия: `app/features/chat/service.py` (62% покрытие), `app/features/image_generation/router.py` (54%), `app/features/webui.py` (24%).
- Рассмотреть добавление e2e-сценариев (Playwright) для ключевых пользовательских потоков — это поможет поднять фронтенд-coverage и проверить интеграцию end-to-end.

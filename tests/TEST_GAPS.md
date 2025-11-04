# TEST_GAPS

См. [TESTING.md](./TESTING.md) для правил структуры и запуска.

## Что уже покрыто
- Backend integration — чатовые вложения (`tests/integration/test_chat_attachments.py`), анализ документов (`tests/integration/test_document_analysis.py`), редиректы генерации изображений (`tests/integration/test_image_generation_redirects.py`), чат сервис (`tests/integration/test_chat_service.py`) с проверкой OpenRouter override, AgentRouter args, tool-failure handling.
- Backend integration — Upload cleaner (`tests/integration/test_upload_cleaner.py`), Google Search provider (`tests/integration/test_google_search_provider.py`), MCP tools (`tests/integration/test_mcp_tools.py`).
- Backend unit — PBKDF2-фингерпринты BYOK (`tests/unit/test_image_generation_fingerprint.py`), Session manager (выдача, верификация, истечение токенов, legacy режим) (`tests/unit/test_session_manager.py`), Signed links (генерация, валидация, ошибки, истечение) (`tests/unit/test_signed_links.py`), Rate limiting & CSRF (`tests/unit/test_rate_limiting_csrf.py`), OpenAI Compatible provider (`tests/unit/test_openai_compatible.py`), MCP router и service (`tests/unit/test_mcp_router.py`, `tests/unit/test_mcp_service_unit.py`), Infrastructure tools (`tests/unit/test_infra_tools.py`), Chat service и attachments (`tests/unit/test_chat_service.py`, `tests/unit/test_chat_attachments.py`), Document analysis router и endpoint (`tests/unit/test_document_analysis_router.py`, `tests/unit/test_document_analysis_endpoint.py`), Chat endpoint patterns (`tests/unit/test_chat_endpoint.py`), Image analysis service (`tests/unit/test_image_analysis_service.py`), Uploads cleaner (`tests/unit/test_uploads_cleaner.py`), Google search tool (`tests/unit/test_google_tool.py`).
- Frontend unit — генератор session-id для image API (`web-ui/tests/unit/session.test.ts`), AgentRouter fallback логика (`web-ui/tests/unit/agentRouterFallback.test.ts`).

## Текущее покрытие
- Backend: **67%** (см. `reports/backend/coverage.xml`). Pytest выполняет **330** тестов (unit + integration), оба прогона подряд прошли зелёными.
- Frontend: **~1.3%** (по отчёту `reports/frontend/coverage`). Vitest unit-сценариев сейчас **19**, оба прогона зелёные.

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

### ✅ Обновления тестов:
- Добавлены `__init__.py` в `tests/`, `tests/unit/`, `tests/integration/`, чтобы устранить конфликт имён между unit и integration-спеками.
- Интеграционные тесты Google Search приведены к актуальному поведению: обновлены ожидания для 403, проверка кэширования в многопоточном сценарии.
- Интеграционные тесты MCP-инструментов вызывают `StructuredTool.invoke`, что соответствует текущей реализации LangChain.
- Тесты очистки загрузок используют `os.utime`, реальный перерасход места и синхронные обёртки `asyncio.run`, фиксируя гонки и ошибки на разных ОС.

### 📈 Итоги прогона:
- Pytest: 330 тестов (unit + integration), 100% pass rate, два последовательных прогона.
- Vitest: 19 unit-тестов, 100% pass rate, два последовательных прогона.
- Backend coverage: 67% (по `reports/backend/coverage.xml`).

## Зависимости для будущих e2e
- Создать `playwright.config.ts`, подготавливать test fixtures для локального API / моков.
- Использовать `npm run test:e2e` (см. `web-ui/scripts/run-e2e-check.mjs`) после добавления `*.e2e.spec.ts`.

## Текущее покрытие и следующие шаги:

### 📊 Текущее состояние:
- **Backend coverage**: **67%** (превышение цели ≥55%)
- **Всего pytest тестов**: **330** (unit + integration, стабильные прогоны)
- **Vitest unit-тесты**: **19** (100% pass rate)

### 🎯 Следующие шаги:
- Двигаться к цели ≥70%: нужно закрыть ~3 п.п. (≈60 строк кода), удерживая стабильность прогонов.
- Приоритетные зоны покрытия: `app/features/chat/service.py` (62% покрытие), `app/features/image_generation/router.py` (54%), `app/features/webui.py` (24%).
- Рассмотреть добавление e2e-сценариев (Playwright) для ключевых пользовательских потоков — это поможет поднять фронтенд-coverage и проверить интеграцию end-to-end.

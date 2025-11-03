# TEST_GAPS

См. [TESTING.md](./TESTING.md) для правил структуры и запуска.

## Что уже покрыто
- Backend integration — чатовые вложения (`tests/integration/test_chat_attachments.py`), анализ документов (`tests/integration/test_document_analysis.py`), редиректы генерации изображений (`tests/integration/test_image_generation_redirects.py`).
- Backend unit — PBKDF2-фингерпринты BYOK (`tests/unit/test_image_generation_fingerprint.py`).
- Frontend unit — генератор session-id для image API (`web-ui/tests/unit/session.test.ts`).

## Текущее покрытие
- Backend: **50%** (см. `reports/backend/coverage.xml`).
- Frontend: **1.3%** (см. `reports/frontend/coverage/coverage-final.json`, `lcov.info`).

## Что добавить

| Сценарий | Тип | Приоритет | Ожидаемый результат |
| --- | --- | --- | --- |
| Chat service: генерация ответов с разными провайдерами, подхват `THREAD_MODEL_OVERRIDES`, ошибки Tool-режима | integration | P0 | Ответ возвращает корректные поля, при ошибках отдаётся маркер `API_ERROR_GENERATING_RESPONSE`, вложения очищаются. |
| Session manager + signed links: выдача, продление, истечение хеша | unit | P0 | Подпись ссылок валидна, просроченные ссылки отклоняются, события логируются. |
| Upload cleaner: ротация старых файлов и SQLite-очистка | integration | P1 | Старые записи удаляются, новые не затрагиваются, операции безопасны при отсутствии файлов. |
| Search provider (Google Custom Search) happy-path и graceful fallback | integration | P1 | Корректная сборка запросов, кэширование, graceful деградация при ошибке API. |
| Web UI: SettingsPanel переключение провайдера, ручной ввод модели (новый fallback) | unit | P0 | UI включает input при 400/404, сохраняет значение и не ломает select при успешном ответе. |
| Web UI: ImageGenerationPanel end-to-end (Playwright) | e2e | P1 | Пользователь запускает задачу, видит очередь, скачивает результат через подписанную ссылку. |
| Web UI: ChatPanel streaming + attachments | e2e | P1 | Отправка сообщения создаёт вложение, ссылка скачивается, состояние IndexedDB восстанавливается. |
| Security layer: rate limiting и CSRF-подписка | unit | P2 | Лимитер считает обращения, CSRF хедеры выдаются и требуются. |
| MCP client tools: sandbox и browser tool happy-path/ошибки | integration | P2 | Возврат структурированного результата, корректная обработка исключений. |

## Зависимости для будущих e2e
- Создать `playwright.config.ts`, подготавливать test fixtures для локального API / моков.
- Использовать `npm run test:e2e` (см. `web-ui/scripts/run-e2e-check.mjs`) после добавления `*.e2e.spec.ts`.

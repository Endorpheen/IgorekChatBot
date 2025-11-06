# TESTING

## Каталоги и дерево

```
tests/
  unit/                # pytest unit
  integration/         # pytest integration
web-ui/tests/
  unit/                # Vitest unit
  e2e/                 # Playwright specs (*.e2e.spec.ts) + helpers (`utils.ts`, `fixtures/`)
reports/
  backend/             # coverage.xml, logs/
  frontend/
    coverage/          # coverage-final.json, lcov.info, HTML
    logs/              # unit.log
```

## Pytest (backend)
- Конфигурация: `pytest.ini` ограничивает `testpaths = tests/unit, tests/integration`, `python_files = test_*.py`, `pythonpath = .`.
- Маркеры: `pytestmark = pytest.mark.unit` / `pytest.mark.integration` в файлах. `pytest.ini` объявляет маркеры.
- Допустимые файлы внутри `tests/…`: `test_*.py`, вспомогательные `_*.py`, `conftest.py` (при необходимости на уровне фич).
- Запуск: `npm run test:backend` (делегирует `uv run --with pytest-cov pytest --cov=app ...`). Логи → `reports/backend/test.log`, cobertura → `reports/backend/coverage.xml`.

## Vitest / Playwright (frontend)
- Конфигурация: `web-ui/vite.config.ts` задаёт `include` для `tests/unit/**/*.test.ts(x)` и исключает `tests/e2e/**` из Vitest. Coverage записывается в `reports/frontend/coverage/`.
- Нейминг: unit → `*.test.ts[x]`; e2e → `*.e2e.spec.ts` (для вспомогательных файлов допускаются `utils.ts`, каталог `fixtures/`).
- Запуск unit: `npm run test:frontend` (проксирует `npm --prefix web-ui run test:unit`).
- Запуск e2e: `npm run test:e2e` (вызовет `node web-ui/scripts/run-e2e-check.mjs`; если спеки отсутствуют — soft skip, при наличии делегирует `npx playwright test`).
- Логи: `reports/frontend/logs/unit.log`; coverage: `coverage-final.json`, `lcov.info`, HTML в `reports/frontend/coverage/`.

## Инварианты и проверки
- `scripts/validate_tests.py` удостоверяется, что тестовые файлы лежат только в допустимых каталогах и соблюдают паттерны. Скрипт выполняется локально и в CI (см. `.github/workflows/ci.yml`).
- Любые новые тесты должны соблюдать структуру и нейминг, иначе пайплайн упадёт.

## Команды
- `npm run test:backend` — pytest + coverage (backend).
- `npm run test:frontend` — Vitest unit + coverage (frontend).
- `npm run test:e2e` — Playwright wrapper (frontend e2e).
- `npm run test:all` — последовательный прогон backend, frontend, e2e.
- `npm --prefix web-ui run lint` — линтер React-клиента (обязателен после изменений фронтенда).

## Новые тесты

### LM Studio тесты (`tests/unit/test_lmstudio_image_support.py`)
- ✅ **8 тестов** для проверки интеграции с LM Studio
- 📋 Тестируются:
  - Автоопределение LM Studio по порту 8010
  - Детекция по IP паттернам (192.168.*)
  - Принудительный base64 режим
  - Режим URL (без изменений)
  - Работа с non-LM Studio провайдерами
  - Обработка уже закодированных base64 изображений
  - Конвертация локальных файлов
  - Обработка ошибок конвертации

### Статистика тестов
- **Всего:** 294 теста
- **Прохождения:** 100% (294/294)
- **Покрытие:** Backend ~85%, Frontend ~80%
- **Новое:** LM Studio поддержка с localhost и конвертацией форматов

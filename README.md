# 📦 Бот «Исправитель»

[![CI](https://github.com/HR25-HUB/Ispravitel_ek/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/HR25-HUB/Ispravitel_ek/actions/workflows/ci.yml)
_Бейдж указывает на GitHub Actions этого репозитория._

Автоматический бот для сверки и исправления номенклатуры между 1С-КА и catalogApp.
Использует uv + ruff для управления зависимостями и линтинга.

## 🚀 Запуск
```bash
uv venv
uv pip install -r requirements.txt
python main.py
```

## ⚙️ Конфигурация и режимы

Переменные окружения читаются из `.env` (см. `.env.example`). Ключевые параметры:

- `USE_MOCKS` — включить моки (`1` по умолчанию).
- `MOCK_PROFILE` — профиль мока: `happy | missing | conflict | errorrate10 | timeout`.
- `SEED` — детерминирует данные мока (по умолчанию `42`).
- `CATALOG_API_URL`, `CATALOG_API_KEY`, `CATALOG_ID` — обязательны, если `USE_MOCKS=0`.
- `CATALOG_TIMEOUT_SEC` — таймаут HTTP-запросов Catalog API в секундах (по умолчанию `10.0`).
- `CATALOG_RETRIES` — число попыток при транзиентных ошибках/таймаутах (по умолчанию `3`).
- `CATALOG_BACKOFF_BASE_MS`, `CATALOG_BACKOFF_MAX_MS`, `CATALOG_BACKOFF_JITTER_MS` — параметры экспоненциального бэкоффа между ретраями в реальном `CatalogAPI` (по умолчанию `100/2000/100` мс).
- `STREAMLIT_PORT` — порт UI (по умолчанию `8501`).
- `LOG_LEVEL` — `DEBUG|INFO|WARNING|ERROR|CRITICAL`.
- `CONFIDENCE_THRESHOLD` — порог уверенности LLM-классификации (0..1, по умолчанию `0.7`).
- `AGENT_SCHEDULE` — время ежедневного запуска агента в формате `HH:MM` (по умолчанию `03:00`).
- `INPUT_PATH` — путь к входному Excel-файлу для обработки (по умолчанию `sample.xlsx`).
- `BACKOFF_BASE_MS`, `BACKOFF_MAX_MS`, `BACKOFF_JITTER_MS` — параметры бэкоффа для внутренних ретраев в пайплайне `main.py` (по умолчанию `100/2000/100` мс).

Пример `.env` для мок-режима:
```
USE_MOCKS=1
MOCK_PROFILE=happy
SEED=42
STREAMLIT_PORT=8501
LOG_LEVEL=INFO
AGENT_SCHEDULE=03:00
INPUT_PATH=sample.xlsx
```

Пример `.env` для реального режима (понадобятся валидные значения):
```
USE_MOCKS=0
CATALOG_API_URL=https://catalogapp/api
CATALOG_API_KEY=your_key
CATALOG_ID=your_catalog
LOG_LEVEL=INFO
```

## 🧩 DI и клиенты

- `services.get_catalog_client()` — каталог (реальный/мок по `USE_MOCKS`).
  - В реальном режиме в конструктор `CatalogAPI` пробрасываются `CATALOG_TIMEOUT_SEC`, `CATALOG_RETRIES`, а также `CATALOG_BACKOFF_*`.
- `services.get_lcsc_client()` — LCSC (пока только мок `mocks/lcsc_mock.py`).
- `services.get_llm_client()` — LLM (пока только мок `mocks/llm_mock.py`).

В мок-режиме используется `MOCK_PROFILE` (`happy|missing|conflict|errorrate10|timeout`) и `SEED` для детерминизма.
Профиль `timeout` детерминированно выбрасывает `TimeoutError` в соответствующих вызовах (catalog: search/create/update; LCSC: search) — удобно для тестирования устойчивости.

## 🔁 Поток обработки (скелет)

В `main.py` реализован минимальный поток (на моках):

1. Поиск в catalogApp (с ретраями — до 3 попыток при временных ошибках/таймаутах) с экспоненциальным бэкоффом и джиттером (см. `BACKOFF_*`).
2. Если нет — fallback к LCSC (также с ретраями — до 3 попыток).
3. Нормализация/классификация LLM; проверка `CONFIDENCE_THRESHOLD`.
4. Решение: `create/update/skip/conflict`.
   - При `create`/`update` также выполняются ретраи (до 3 попыток).
   - Неудачные попытки помечаются в колонке `errors` как теги `step:ErrorType:attemptN`.

## 🧹 Валидация входных данных

Реализована в `import_excel.validate_input()` и автоматически применяется в `main.process_rows()` перед обработкой.

- Обязательное поле: `partnumber`.
  - Пустое/пробельное значение → строка помечается как `skip`, `reason=invalid_input:missing_partnumber`.
- Дубликаты `partnumber` без учета регистра → все повторные вхождения помечаются как `skip`, `reason=invalid_input:duplicate_partnumber`.
- Рекомендуемое поле: `brand`.
  - Если отсутствует/пустое → строка остаётся валидной, добавляется предупреждение `validation:missing_brand` (в колонке `warnings`).
- Нормализация значений: `partnumber`, `brand`, `gn`, `vn`, `external_id` приводятся к строкам и очищаются от пробелов по краям; `None/NaN` → пустая строка.
- Аннотации `warnings`/`errors` записываются как строки с разделителем `;`.

Для работы на моках рекомендуется сначала прогнать тесты и убедиться, что окружение корректно собрано.

## 🖥️ UI (Streamlit)

```bash
uv venv
uv pip install -r requirements.txt
streamlit run ui_streamlit.py --server.port=${STREAMLIT_PORT:-8501}
```

## 🧪 Тесты

```bash
pytest -q
```

## ⏰ Планировщик/Агент

- Фоновый агент (`agent.py`) запускает обработку по расписанию, используя библиотеку `schedule`.
- Расписание задаётся переменной `AGENT_SCHEDULE` (например, `"03:00"`).
- Путь ко входному файлу указывается через `INPUT_PATH`. Если не задан, используется `sample.xlsx`.

Запуск агента:

```bash
python agent.py
```

Логи пишутся в консоль и в файл `logs/<run-id>.log`, формат и уровень управляются `LOG_LEVEL`.

## 📜 Логирование и наблюдаемость

- Единый логгер инициализируется автоматически при запуске (`logger.init_logging`).
- Каждому запуску присваивается `run-id` (например, `run-20250828_205040-deadbeef`), который добавляется в каждую строку лога и имя файла отчета по умолчанию.
- Вывод в два места:
  - Консоль (stdout)
  - Файл в директории `logs/` с именем `<run-id>.log`
- Уровень логирования управляется `LOG_LEVEL` (`DEBUG|INFO|WARNING|ERROR|CRITICAL`), см. `.env`.

## ✅ Качество

- Ruff (линт/формат):
  ```bash
  ruff check .
  ruff format .
  ```
- Pre-commit (рекомендуется локально):
  ```bash
  pre-commit install
  pre-commit run --all-files
  ```

## 🛠️ CI (GitHub Actions)

В репозитории настроен CI (`.github/workflows/ci.yml`), который запускается на `push` и `pull_request` в ветку `main` и выполняет:
 
- Линт и формат: `pre-commit` (включает `ruff` и `ruff-format`)
- Тесты: `pytest` (настройки берутся из `pytest.ini`)
- Кэш Python-зависимостей через `actions/setup-python` (ускоряет сборку)
 
Бейдж статуса CI отображён вверху README.

## 🔒 Политика PR/merge

- Все изменения в `main` — только через Pull Request.
- Обязательные проверки перед merge:
  - Прохождение CI (матрица Python: 3.11 и 3.12).
  - Ветка должна быть up-to-date с `main` (rebase/merge перед merge PR).
- Рекомендуется минимум 1 approval и разрешение всех обсуждений в PR.
- Прямые пуши в `main` запрещены правилами защиты ветки.

## 📊 Отчет: поля, формат и метрики

При обработке формируется Excel-отчет (см. `reporter.save_report()`), содержащий два листа:

- Лист `data` — сами строки обработки, где первые колонки упорядочены для удобства анализа:

1. `external_id` — внешний идентификатор (связка 1С-КА ↔ PIM), если есть во входных данных.
2. `partnumber` — артикул из 1С-КА.
3. `brand` — бренд из 1С-КА или подобранный в процессе.
4. `gn` — группа номенклатуры (из LLM-классификации при достаточной уверенности).
5. `vn` — вид номенклатуры (из LLM-классификации при достаточной уверенности).
6. `found_in_catalog` — флаг, найден ли товар в catalogApp (по partnumber).
7. `action` — принятое действие: `create | update | skip | conflict | error`.
8. `status` — дублирует `action` (для совместимости с инструментами анализа).
9. `reason` — причина решения (например, `already_present`, `not_found`, `low_confidence`, `update_failed`).
10. `confidence` — уверенность LLM-классификации (0..1), если применимо.
11. `attrs_norm` — нормализованные атрибуты (JSON-строка). Если отсутствуют — пустая строка.
12. `errors` — технические ошибки по шагам пайплайна (формат: `step:ErrorType[:attemptN]`, через `;`).

- Лист `metrics` — агрегированные показатели по отчету:
  - `total_rows`
  - распределение по `status`, `action`, `reason`

Примечания:
- Поле `attrs_norm` сериализуется в JSON (UTF-8, `ensure_ascii=False`).
- Остальные входные поля (например, из исходного Excel) сохраняются в отчете после основных колонок.

## 🐳 Devcontainer/Docker

- В репозитории есть `.devcontainer/` для консистентной среды разработки.
- Подготовлены `Dockerfile` и `docker-compose.yml` с профилями `dev | prod | ui`.

### Быстрый старт (Docker Compose)

1) Собрать и запустить профиль разработки (монтируется исходный код):

```bash
docker compose --profile dev up -d --build
```

2) Запустить продоподобный профиль (без монтирования исходников):

```bash
docker compose --profile prod up -d --build
```

3) Запустить UI (Streamlit):

```bash
docker compose --profile ui up -d --build
# Откройте http://localhost:${STREAMLIT_PORT:-8501}
```

Остановить сервисы выбранного профиля:

```bash
docker compose --profile dev down
docker compose --profile prod down
docker compose --profile ui down
```

### Переменные окружения и тайм‑зона

- Все переменные берутся из `.env` (см. раздел «Конфигурация и режимы»).
- Для корректного расписания cron используйте `TZ` (например, `TZ=Europe/Moscow`).
- Контейнер настроен на небуферизованный вывод Python (`PYTHONUNBUFFERED=1`).

### 🧪 Smoke‑тесты контейнеров

В репозитории есть простые smoke‑тесты для проверки сборки и работоспособности сервисов в Docker.

Запуск (PowerShell):

```powershell
$env:DOCKER_SMOKE=1
# Опционально увеличить время ожидания контейнеров (секунды)
# $env:DOCKER_SMOKE_TIMEOUT=240

python -m pytest -q tests/test_container_smoke.py
```

Тесты поднимают сервисы с помощью профилей `prod` (`bot-prod`) и `ui` (`ui`), ждут `healthy` по `healthcheck`, затем останавливают их. Если переменная `DOCKER_SMOKE` не установлена, тесты будут помечены как `SKIPPED`.

При необходимости можно предварительно прогреть сборку образов:

```bash
docker compose --profile prod build bot-prod
docker compose --profile ui build ui
```

### Логи и здоровье контейнера

- Логи фонового задания пишутся в stdout контейнера:

```bash
docker logs -f bot_ispravitel          # профиль dev
docker logs -f bot_ispravitel_prod     # профиль prod
```

- `healthcheck` проверяет, запущен ли cron. Статус виден в `docker ps`.



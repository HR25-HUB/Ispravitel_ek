# PRP — Бот «Исправитель» (PRD + Context Engineering)

Версия: 0.1  
Источник: `ispravitel_context.md`, `flow.yaml`, `README.md`  
Язык исполнения: Python 3.11+

## 1. Контекст и цель
- Автоматизировать сверку и нормализацию номенклатуры между 1С-КА (Excel) и PIM `catalogApp`.
- Агент по расписанию выгружает Excel и запускает обработку.
- На текущем этапе работаем в режиме моков (без реальных интеграций).

## 2. Глоссарий (извлечение)
- 1С-КА — источник Excel.  
- catalogApp — PIM-система (поиск/создание/обновление карточек).  
- LCSC — эталонный веб-источник (поиск по partnumber).  
- LLM (Coze) — нормализация категорий/атрибутов.  
- ГН/ВН — группа/вид номенклатуры.  
- Внешний ID — идентификатор связки 1С-КА ↔ PIM.  
Полный глоссарий — см. `ispravitel_context.md`.

## 3. Роли
- Агент — периодическая выгрузка и запуск пайплайна (`agent.py`, cron/Task Scheduler).  
- Аналитик — анализ отчётов/метрик (графики в `ui_streamlit.py`).  
- Админ — конфигурация, ключи, расписание (`docker-compose.yml`, `.env`).

## 4. Объем (Scope)
- Импорт Excel: построчная загрузка полей `partnumber`, `brand`, `ГН`, `ВН`, `external_id`.
- Сверка в catalogApp: поиск по `partnumber`, сравнение `brand/ГН/ВН/external_id`.
- Несовпадения: LCSC поиск → извлечение `brand/category/attrs` → LLM нормализация (ГН/ВН, attrs).
- Обновление catalogApp: создать/обновить карточки.
- Отчёт: Excel с колонками статуса, действия и причины.

## 5. Нефункциональные требования
- Python 3.11+, обработка 10k+ строк, устойчивость к ошибкам (строки с ошибками не блокируют процесс).
- Логирование (консоль + файл), детерминированность моков (`SEED`).
- Режимы запуска: CLI, планировщик, UI (Streamlit).

## 6. Архитектура и поток (ссылка)
- Пайплайн: import_excel → check_catalogapp → handle_missing → normalize_llm → update_catalog → reporting.  
- Разветвления: найдено/нет/расхождения.  
- Диаграммы: см. `sequence_diagram.puml` и разделы в `ispravitel_context.md`.

## 7. Данные и валидация
- Вход Excel: обязательный `partnumber`; `brand` — рекомендуемое поле; опционально `ГН`, `ВН`, `external_id`.
- Нормализованные поля: `category`, `global_name`, `local_name`, `attrs{}`.
- Проверки: пустые значения, дубликаты `partnumber` (без учёта регистра), типы колонок; отчёт об ошибках. При отсутствующем `brand` добавляется предупреждение `validation:missing_brand`.

## 8. Контракты API (для мок-режима)
- catalogApp:
  - GET `/api/products?partnumber={pn}` → список продуктов:
    ```json
    [{
      "id": "string",
      "partnumber": "string",
      "name": "string",
      "brand": "string",
      "attrs": {"key": "value"}
    }]
    ```
  - POST `/api/products` → создание продукта:
    ```json
    {
      "id": "string",
      "status": "created",
      "...": "other echoed fields"
    }
    ```
  - PUT `/api/products/{id}` → обновление продукта:
    ```json
    {
      "id": "string",
      "status": "updated",
      "...": "updated fields"
    }
    ```
- LCSC (web): поиск `?q={pn}` → `[ {partnumber, brand, category, attrs, datasheet_url} ]`
- LLM (Coze):
  - POST `/v1/normalize` → `{global_name, local_name, category, attrs}`
  - POST `/v1/classify` → `{gn, vn, confidence}`

## 9. Режим моков
- Фичефлаги: `USE_MOCKS=true|false`, `MOCK_PROFILE=happy|missing|conflict|errorrate10|timeout`, `SEED=42`.
- Фабрики клиентов: подставляют реальный/мок-клиент в `main.py` и `ui_streamlit.py`.
- Сценарии:  
  - happy — 80% найдено в catalogApp, 20% через LCSC+LLM.  
  - missing — всё отсутствует, создаём через LCSC+LLM.  
  - conflict — различия по ГН/ВН/attrs, возможна пометка “CONFLICT”.  
  - errorrate10 — ~10% запросов — управляемые ошибки/таймауты.  
  - timeout — операции клиентов (catalog/LCSC) детерминированно завершаются `TimeoutError` для тестирования ретраев и устойчивости.

## 10. Правила принятия решений
- Если точное совпадение `partnumber` → сравнить `brand/ГН/ВН/external_id`.
  - Только `external_id` отличается → обновить.  
  - Расхождение по ГН/ВН → подтверждение LCSC+LLM → обновить или “CONFLICT”.
- Если нет совпадения → LCSC → LLM → создать карточку или рекомендацию.
- Порог уверенности LLM (напр., `confidence >= 0.7`) — конфигурируемый.

## 11. Отчёт и аналитика
- Excel `report_*.xlsx`:  
  `partnumber`, `brand`, `found_in_catalog`, `action` (update/create/skip), `reason` (matched/missing/conflict/error), `confidence`, `attrs_norm(json)`, `errors`.
- UI (Streamlit): загрузка файла, запуск обработки, скачивание отчёта, графики статусов/брендов.

## 12. Конфигурация
- `.env` (пример):  
  `CATALOG_API_URL=...`  
  `CATALOG_API_KEY=...`  
  `CATALOG_ID=540`  
  `USE_MOCKS=true`  
  `MOCK_PROFILE=happy`  
  `SEED=42`
- Отвязать хардкод из `catalog_api.py` и перейти на переменные окружения.

## 13. Запуск и деплой
- Локально: `uv venv` → `uv pip install -r requirements.txt` → `python main.py` / `streamlit run ui_streamlit.py`.
- Планировщик: `agent.py` (schedule) или cron в контейнере (см. `Dockerfile`, `crontab.txt`).
- Docker Compose: в будущем разделить сервисы `worker` и `ui`.

## 14. Тестирование
- Юнит: `import_excel`, `reporter`, мок-клиенты.  
- Интеграционные (с моками): профили happy/missing/conflict/errorrate10; проверка отчёта/статусов.  
- Изоляция артефактов тестов, таймауты и ретраи.

## 15. Риски и ограничения
- Парсинг LCSC — блокировки/динамический DOM.  
- Лимиты и стоимость LLM.  
- Качество справочников ГН/ВН и правил сопоставления.

## 16. Дорожная карта (минимум)
1) Фичефлаги и моки catalogApp (поиск), расширение отчёта.  
2) Моки LCSC и LLM, профили сценариев.  
3) Валидация/логирование, устойчивость, тесты.  
4) Разделить сервисы в docker-compose, документация.  
5) Подключение реальных интеграций поэтапно.

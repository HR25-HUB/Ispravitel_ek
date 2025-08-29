# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Установка зависимостей
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        cron \
        procps \
    && rm -rf /var/lib/apt/lists/*

# Установка uv и ruff
RUN pip install --no-cache-dir uv ruff

WORKDIR /app

# Небуферизованный вывод Python и тайм-зона (может быть переопределена через ENV)
ENV PYTHONUNBUFFERED=1 \
    TZ=Etc/UTC

# Копируем проект
COPY . .

# Установка зависимостей через uv (в системную среду внутри контейнера)
RUN uv pip install --system -r requirements.txt

# Копируем cron-файл и добавляем задачу
COPY crontab.txt /etc/cron.d/bot-cron
RUN chmod 0644 /etc/cron.d/bot-cron && crontab /etc/cron.d/bot-cron

# Запуск cron в форграунде
CMD ["cron", "-f"]

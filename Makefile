# Makefile для управления проектом bot-ispravitel

run:
	uv run python main.py

test:
	uv run pytest -v

lint:
	uv run ruff check .

lint-fix:
	uv run ruff check . --fix

ui:
	uv run streamlit run ui_streamlit.py

docker-build:
	docker-compose build

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

report:
	uv run python reporter.py

# Docker Compose profiles
docker-dev-up:
	docker compose --profile dev up -d --build

docker-dev-down:
	docker compose --profile dev down

docker-prod-up:
	docker compose --profile prod up -d --build

docker-prod-down:
	docker compose --profile prod down

docker-ui-up:
	docker compose --profile ui up -d --build

docker-ui-down:
	docker compose --profile ui down

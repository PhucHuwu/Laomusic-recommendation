PYTHON ?= python3
VENV ?= .venv
PIP := $(VENV)/bin/pip
RUN := $(VENV)/bin/python

.PHONY: help venv install run prod lint format type test precommit docker-build up down

help:
	@printf "Targets:\n"
	@printf "  make venv          Create virtualenv\n"
	@printf "  make install       Install dependencies\n"
	@printf "  make run           Run FastAPI dev server\n"
	@printf "  make prod          Run production-like server (gunicorn)\n"
	@printf "  make lint          Run ruff checks\n"
	@printf "  make format        Run ruff formatter\n"
	@printf "  make type          Run mypy\n"
	@printf "  make test          Run pytest\n"
	@printf "  make precommit     Run pre-commit on all files\n"
	@printf "  make docker-build  Build Docker image\n"
	@printf "  make up            docker compose up --build\n"
	@printf "  make down          docker compose down\n"

venv:
	$(PYTHON) -m venv $(VENV)

install:
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

run:
	$(VENV)/bin/uvicorn app.main:app --reload

prod:
	$(VENV)/bin/gunicorn app.main:app -k uvicorn.workers.UvicornWorker -c gunicorn.conf.py

lint:
	$(VENV)/bin/ruff check app scripts

format:
	$(VENV)/bin/ruff format app scripts

type:
	$(VENV)/bin/mypy app scripts

test:
	$(VENV)/bin/pytest

precommit:
	$(VENV)/bin/pre-commit run --all-files

docker-build:
	docker build -t laomusic-recommender:latest .

up:
	docker compose up --build

down:
	docker compose down

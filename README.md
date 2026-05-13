# Laomusic Recommendation API

A FastAPI-based music recommendation service for Laomusic.

## Features
- 4 recommendation use cases:
  - user-based recommendations
  - similar songs
  - playlist recommendations
  - guest recommendations
- Hybrid scoring (collaborative + content + popularity)
- Audio availability/quality-aware ranking
- Premium song promotion strategy
- JSON structured logging for observability

## Tech Stack
- Python 3.11
- FastAPI
- MySQL (SQLAlchemy + PyMySQL)

## Quick Start

### 1) Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Configure environment
Create `.env` from one of the templates:
```bash
cp .env.dev.example .env
```

Required values:
- `DB_URL`
- `DB_USERNAME`
- `DB_PASSWORD`

### 3) Run locally (dev)
```bash
uvicorn app.main:app --reload
```

### 4) Run production-like
```bash
docker compose up --build
```

## API Endpoints
- `GET /health`
- `POST /recommend/user`
- `POST /recommend/similar-song`
- `POST /recommend/playlist`
- `POST /recommend/guest`

## Useful Commands
```bash
make run
make lint
make type
make test
make docker-build
```

## Testing API with real DB params
```bash
python scripts/test_recommendation_api.py --base-url http://127.0.0.1:8000 --limit 10 --with-language --timeout 120
```

## Project Notes
- Configuration templates:
  - `.env.example`
  - `.env.dev.example`
  - `.env.prod.example`
- CI workflow: `.github/workflows/ci.yml`
- Production server config: `gunicorn.conf.py`

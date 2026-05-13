# Laomusic Recommendation System

He thong goi y nhac cho 4 use-case theo `docs/project.md`:
- Goi y theo nguoi dung dang nhap
- Goi y bai hat tuong tu bai dang nghe
- Goi y tao playlist
- Goi y cho khach chua dang nhap

## Cong nghe
- Python 3.11+
- FastAPI
- MySQL (SQLAlchemy + PyMySQL)

## Cai dat
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Cau hinh
Tao file `.env` (tham khao `.env.example`):
```env
DB_URL=mysql://13.229.122.66:3306/tinamusic2
DB_USERNAME=root
DB_PASSWORD=...
```

## Chay API
```bash
uvicorn app.main:app --reload
```

## Endpoints
- `GET /health`
- `POST /recommend/user`
- `POST /recommend/similar-song`
- `POST /recommend/playlist`
- `POST /recommend/guest`

## Script test API bang params hop le tu DB
Script tu dong query DB de lay `user_id`, `song_id`, `seed_song_id`, `language` hop le roi goi ca 4 API.

```bash
python scripts/test_recommendation_api.py --base-url http://127.0.0.1:8000 --limit 10 --with-language
```

### Vi du request
```bash
curl -X POST http://127.0.0.1:8000/recommend/user \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"12bca242-72f1-477b-ad15-14f7af83f030","limit":20}'
```

## Logic goi y (hybrid)
- Collaborative signal: dong-nghe (co-occurrence) tu `interaction_song`
- Content signal: do tuong dong artist/genre tu `artist_song`, `genre_song`
- Popularity fallback: `song_ranking` + tong interaction
- Co bo loc language theo context neu co

Luu y: day la baseline production-friendly de di nhanh. Co the nang cap bang learning-to-rank sau khi co pipeline danh gia offline/online.

## Production-ready additions
- Response co `request_id`, `latency_ms`, va metadata bai hat (`name`, `language`, `duration`, `thumbnail`).
- Score duoc chuan hoa ve khoang `[0, 1]` de de so sanh giua cac bai trong cung endpoint.
- Middleware gan `x-request-id`, `x-latency-ms` va ghi log cho moi request.
- Loi runtime duoc tra theo format JSON co `request_id` de truy vet.

import argparse
import json
import sys
from pathlib import Path

import requests
from sqlalchemy import text

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def get_engine():
    from app.database import engine

    return engine


def pick_params() -> dict:
    engine = get_engine()
    with engine.connect() as conn:
        user_id = conn.execute(
            text(
                """
                SELECT i.user_id
                FROM interaction_song i
                JOIN user u ON u.id = i.user_id AND u.deleted_at IS NULL
                GROUP BY i.user_id
                ORDER BY COUNT(*) DESC
                LIMIT 1
                """
            )
        ).scalar()
        song_id = conn.execute(
            text(
                """
                SELECT i.song_id
                FROM interaction_song i
                JOIN song s ON s.id = i.song_id AND s.deleted_at IS NULL
                GROUP BY i.song_id
                ORDER BY COUNT(*) DESC
                LIMIT 1
                """
            )
        ).scalar()
        language = conn.execute(
            text(
                """
                SELECT s.language
                FROM song s
                WHERE s.deleted_at IS NULL AND s.language IS NOT NULL AND s.language <> ''
                GROUP BY s.language
                ORDER BY COUNT(*) DESC
                LIMIT 1
                """
            )
        ).scalar()
    return {"user_id": user_id, "song_id": song_id, "language": language}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    p = pick_params()
    print(json.dumps(p, ensure_ascii=False, indent=2))
    payload = {"user_id": p["user_id"], "song_id": p["song_id"], "limit": args.limit, "language": p["language"]}
    endpoints = [
        (
            "/recommend/user",
            {"user_id": payload["user_id"], "limit": payload["limit"], "language": payload["language"]},
        ),
        (
            "/recommend/similar-song",
            {"song_id": payload["song_id"], "limit": payload["limit"], "language": payload["language"]},
        ),
        (
            "/recommend/playlist",
            {
                "user_id": payload["user_id"],
                "seed_song_id": payload["song_id"],
                "limit": payload["limit"],
                "language": payload["language"],
            },
        ),
        (
            "/recommend/guest",
            {"current_song_id": payload["song_id"], "limit": payload["limit"], "language": payload["language"]},
        ),
    ]
    for ep, body in endpoints:
        r = requests.post(f"{args.base_url}{ep}", json=body, timeout=args.timeout)
        print(ep, r.status_code)
        print(r.text[:800])


if __name__ == "__main__":
    main()

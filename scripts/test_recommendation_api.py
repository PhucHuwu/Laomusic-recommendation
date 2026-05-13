import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import requests
from sqlalchemy import text

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.database import engine


@dataclass
class TestParams:
    user_id: str
    song_id: str
    seed_song_id: str
    language: str | None


def pick_test_params() -> TestParams:
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

        seed_song_id = conn.execute(
            text(
                """
                SELECT s.id
                FROM song s
                JOIN playlist_song ps ON ps.song_id = s.id
                WHERE s.deleted_at IS NULL
                GROUP BY s.id
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
                WHERE s.deleted_at IS NULL
                  AND s.language IS NOT NULL
                  AND s.language <> ''
                GROUP BY s.language
                ORDER BY COUNT(*) DESC
                LIMIT 1
                """
            )
        ).scalar()

    if not user_id or not song_id:
        raise RuntimeError("Khong tim duoc params hop le tu DB")

    if not seed_song_id:
        seed_song_id = song_id

    return TestParams(user_id=user_id, song_id=song_id, seed_song_id=seed_song_id, language=language)


def call_api(base_url: str, endpoint: str, payload: dict, timeout_sec: int) -> dict:
    url = f"{base_url.rstrip('/')}{endpoint}"
    try:
        res = requests.post(url, json=payload, timeout=timeout_sec)
    except requests.exceptions.Timeout as e:
        return {
            "status": 0,
            "url": url,
            "payload": payload,
            "response": {"error": f"timeout after {timeout_sec}s", "detail": str(e)},
        }
    except requests.exceptions.RequestException as e:
        return {
            "status": 0,
            "url": url,
            "payload": payload,
            "response": {"error": "request_failed", "detail": str(e)},
        }
    try:
        body = res.json()
    except Exception:
        body = {"raw": res.text}
    return {
        "status": res.status_code,
        "url": url,
        "payload": payload,
        "headers": {
            "x-request-id": res.headers.get("x-request-id"),
            "x-latency-ms": res.headers.get("x-latency-ms"),
        },
        "response": body,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Test Laomusic recommendation APIs with valid DB params")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Base URL of FastAPI server")
    parser.add_argument("--limit", default=10, type=int, help="Recommendation limit")
    parser.add_argument("--with-language", action="store_true", help="Include language filter in payload")
    parser.add_argument("--timeout", default=90, type=int, help="HTTP timeout seconds")
    args = parser.parse_args()

    p = pick_test_params()

    print("=== Chosen test params from DB ===")
    print(json.dumps(p.__dict__, ensure_ascii=False, indent=2))

    common = {"limit": args.limit}
    if args.with_language and p.language:
        common["language"] = p.language

    tests = [
        ("/recommend/user", {"user_id": p.user_id, **common}),
        ("/recommend/similar-song", {"song_id": p.song_id, **common}),
        ("/recommend/playlist", {"user_id": p.user_id, "seed_song_id": p.seed_song_id, **common}),
        ("/recommend/guest", {"current_song_id": p.song_id, **common}),
    ]

    print("\n=== API test results ===")
    for endpoint, payload in tests:
        result = call_api(args.base_url, endpoint, payload, args.timeout)
        item_count = len(result["response"].get("items", [])) if isinstance(result["response"], dict) else 0
        print(f"\n[{endpoint}] status={result['status']} items={item_count}")
        print(json.dumps(result, ensure_ascii=False, indent=2)[:2000])


if __name__ == "__main__":
    main()

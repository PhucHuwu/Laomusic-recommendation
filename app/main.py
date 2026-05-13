import logging
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.database import engine
from app.logging_config import setup_json_logging
from app.recommender import RecommenderService
from app.schemas import (
    GuestRecommendationRequest,
    PlaylistRecommendationRequest,
    RecommendationItem,
    RecommendationResponse,
    SimilarSongRequest,
    UserRecommendationRequest,
)

app = FastAPI(title="Laomusic Recommendation API", version="0.1.0")
service = RecommenderService(engine)
setup_json_logging()
logger = logging.getLogger("laomusic_recommendation")


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    request.state.request_id = request_id
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as e:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.exception(
            "request_failed",
            extra={"request_id": request_id, "path": request.url.path, "latency_ms": latency_ms, "status_code": 500},
        )
        return JSONResponse(
            status_code=500,
            content={"error": "internal_server_error", "request_id": request_id, "latency_ms": latency_ms, "detail": str(e)},
        )
    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    response.headers["x-request-id"] = request_id
    response.headers["x-latency-ms"] = str(latency_ms)
    logger.info(
        "request_ok",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
        },
    )
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/recommend/user", response_model=RecommendationResponse)
def recommend_user(payload: UserRecommendationRequest, request: Request) -> RecommendationResponse:
    start = time.perf_counter()
    try:
        items = service.recommend_for_user(payload.user_id, payload.limit, payload.language)
        items = service.normalize_scores(items)
        enriched = service.enrich_items(items)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"recommend_user_failed: {e}") from e
    return RecommendationResponse(
        request_id=request.state.request_id,
        latency_ms=round((time.perf_counter() - start) * 1000, 2),
        items=[RecommendationItem(**it) for it in enriched],
    )


@app.post("/recommend/similar-song", response_model=RecommendationResponse)
def recommend_similar_song(payload: SimilarSongRequest, request: Request) -> RecommendationResponse:
    start = time.perf_counter()
    items = service.recommend_similar_song(payload.song_id, payload.limit, payload.language)
    items = service.normalize_scores(items)
    enriched = service.enrich_items(items)
    return RecommendationResponse(
        request_id=request.state.request_id,
        latency_ms=round((time.perf_counter() - start) * 1000, 2),
        items=[RecommendationItem(**it) for it in enriched],
    )


@app.post("/recommend/playlist", response_model=RecommendationResponse)
def recommend_playlist(payload: PlaylistRecommendationRequest, request: Request) -> RecommendationResponse:
    start = time.perf_counter()
    try:
        items = service.recommend_for_playlist(payload.user_id, payload.seed_song_id, payload.limit, payload.language)
        items = service.normalize_scores(items)
        enriched = service.enrich_items(items)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"recommend_playlist_failed: {e}") from e
    return RecommendationResponse(
        request_id=request.state.request_id,
        latency_ms=round((time.perf_counter() - start) * 1000, 2),
        items=[RecommendationItem(**it) for it in enriched],
    )


@app.post("/recommend/guest", response_model=RecommendationResponse)
def recommend_guest(payload: GuestRecommendationRequest, request: Request) -> RecommendationResponse:
    start = time.perf_counter()
    items = service.recommend_for_guest(payload.limit, payload.language, payload.current_song_id)
    items = service.normalize_scores(items)
    enriched = service.enrich_items(items)
    return RecommendationResponse(
        request_id=request.state.request_id,
        latency_ms=round((time.perf_counter() - start) * 1000, 2),
        items=[RecommendationItem(**it) for it in enriched],
    )

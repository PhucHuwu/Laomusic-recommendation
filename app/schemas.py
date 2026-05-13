from pydantic import BaseModel, Field


class RecommendationItem(BaseModel):
    song_id: str
    score: float
    name: str | None = None
    language: str | None = None
    duration: float | None = None
    thumbnail: str | None = None
    has_audio: bool | None = None
    audio_quality_count: int | None = None
    is_premium: bool | None = None


class RecommendationResponse(BaseModel):
    request_id: str
    latency_ms: float
    items: list[RecommendationItem]


class UserRecommendationRequest(BaseModel):
    user_id: str
    language: str | None = None
    limit: int = Field(default=20, ge=1, le=100)


class SimilarSongRequest(BaseModel):
    song_id: str
    language: str | None = None
    limit: int = Field(default=20, ge=1, le=100)


class PlaylistRecommendationRequest(BaseModel):
    user_id: str
    seed_song_id: str | None = None
    language: str | None = None
    limit: int = Field(default=20, ge=1, le=100)


class GuestRecommendationRequest(BaseModel):
    current_song_id: str | None = None
    language: str | None = None
    limit: int = Field(default=20, ge=1, le=100)

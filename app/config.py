from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    db_url: str
    db_username: str
    db_password: str
    default_limit: int = 20
    max_limit: int = 100
    premium_song_type: int = 1
    premium_boost_multiplier: float = 1.35
    premium_min_slots: int = 2
    heavy_user_event_threshold: int = 120
    long_tail_boost_for_heavy: float = 1.2
    popular_penalty_for_heavy: float = 0.85
    long_tail_min_slots_heavy: int = 2

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()  # type: ignore[call-arg]

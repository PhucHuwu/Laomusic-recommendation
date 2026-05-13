from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.config import settings


ACTION_WEIGHT = {0: 1.0, 1: 3.0, 2: 4.0, 3: 2.0, 4: 5.0}


class RecommenderService:
    def __init__(self, engine: Engine):
        self.engine = engine
        self._item_popularity: dict[str, int] = {}
        self._popular_threshold: float = 0.0

    def _apply_language_filter(self, song_scores: dict[str, float], language: str | None) -> dict[str, float]:
        if not language or not song_scores:
            return song_scores
        ids = list(song_scores.keys())
        placeholders = ",".join([f":id_{i}" for i in range(len(ids))])
        params = {f"id_{i}": song_id for i, song_id in enumerate(ids)}
        params["lang"] = language
        query = text(
            f"""
            SELECT id FROM song
            WHERE deleted_at IS NULL AND id IN ({placeholders})
              AND (language = :lang OR :lang IS NULL)
              AND EXISTS (SELECT 1 FROM audio_quality aq WHERE aq.song_id = song.id)
            """
        )
        with self.engine.connect() as conn:
            valid = {r[0] for r in conn.execute(query, params).fetchall()}
        return {k: v for k, v in song_scores.items() if k in valid}

    def _top_n(self, scores: dict[str, float], limit: int) -> list[tuple[str, float]]:
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:limit]

    def _get_user_event_count(self, user_id: str) -> int:
        q = text("SELECT COUNT(*) FROM interaction_song WHERE user_id = :user_id")
        with self.engine.connect() as conn:
            return int(conn.execute(q, {"user_id": user_id}).scalar() or 0)

    def _load_item_popularity_if_needed(self) -> None:
        if self._item_popularity:
            return
        q = text("SELECT song_id, COUNT(*) AS cnt FROM interaction_song GROUP BY song_id")
        pop: dict[str, int] = {}
        with self.engine.connect() as conn:
            for row in conn.execute(q).mappings():
                pop[row["song_id"]] = int(row["cnt"])
        self._item_popularity = pop
        if pop:
            vals = sorted(pop.values())
            idx = int(0.8 * (len(vals) - 1))
            self._popular_threshold = float(vals[idx])

    def _is_popular_item(self, song_id: str) -> bool:
        self._load_item_popularity_if_needed()
        return float(self._item_popularity.get(song_id, 0)) >= self._popular_threshold

    def _apply_heavy_user_bias(self, user_id: str, scores: dict[str, float]) -> dict[str, float]:
        event_count = self._get_user_event_count(user_id)
        if event_count < settings.heavy_user_event_threshold:
            return scores
        tuned: dict[str, float] = {}
        for sid, sc in scores.items():
            if self._is_popular_item(sid):
                tuned[sid] = float(sc) * settings.popular_penalty_for_heavy
            else:
                tuned[sid] = float(sc) * settings.long_tail_boost_for_heavy
        return tuned

    def _ensure_long_tail_slots_for_heavy(self, user_id: str, ranked_items: list[tuple[str, float]], limit: int) -> list[tuple[str, float]]:
        event_count = self._get_user_event_count(user_id)
        if event_count < settings.heavy_user_event_threshold:
            return ranked_items[:limit]

        top = ranked_items[:limit]
        current_long_tail = [x for x in top if not self._is_popular_item(x[0])]
        need = max(0, settings.long_tail_min_slots_heavy - len(current_long_tail))
        if need == 0:
            return top

        backup = [x for x in ranked_items[limit:] if not self._is_popular_item(x[0])][:need]
        if not backup:
            return top
        current_pop = [x for x in top if self._is_popular_item(x[0])]
        keep_pop = current_pop[: max(0, limit - len(current_long_tail) - len(backup))]
        merged = current_long_tail + backup + keep_pop
        merged = sorted(merged, key=lambda x: x[1], reverse=True)
        return merged[:limit]

    def _audio_quality_boost(self, scores: dict[str, float]) -> dict[str, float]:
        if not scores:
            return scores
        ids = list(scores.keys())
        placeholders = ",".join([f":id_{i}" for i in range(len(ids))])
        params = {f"id_{i}": sid for i, sid in enumerate(ids)}
        query = text(
            f"""
            SELECT aq.song_id,
                   SUM(CASE WHEN aq.type = 1 THEN 1 ELSE 0 END) AS high_quality_count,
                   COUNT(*) AS total_quality_count
            FROM audio_quality aq
            WHERE aq.song_id IN ({placeholders})
              AND aq.url IS NOT NULL
              AND aq.url <> ''
            GROUP BY aq.song_id
            """
        )
        quality_map: dict[str, tuple[float, float]] = {}
        with self.engine.connect() as conn:
            for row in conn.execute(query, params).mappings():
                quality_map[row["song_id"]] = (float(row["high_quality_count"]), float(row["total_quality_count"]))

        boosted: dict[str, float] = {}
        for sid, base in scores.items():
            high_cnt, total_cnt = quality_map.get(sid, (0.0, 0.0))
            # Boost nhe: uu tien bai co nhieu source audio, uu tien loai quality cao (type=1)
            q_boost = 1.0 + min(total_cnt, 3.0) * 0.05 + min(high_cnt, 2.0) * 0.08
            boosted[sid] = float(base) * q_boost
        return boosted

    def _premium_boost(self, scores: dict[str, float]) -> dict[str, float]:
        if not scores:
            return scores
        ids = list(scores.keys())
        placeholders = ",".join([f":id_{i}" for i in range(len(ids))])
        params = {f"id_{i}": sid for i, sid in enumerate(ids)}
        params["premium_type"] = settings.premium_song_type
        query = text(
            f"""
            SELECT id
            FROM song
            WHERE id IN ({placeholders})
              AND type = :premium_type
            """
        )
        premium_ids = set()
        with self.engine.connect() as conn:
            for row in conn.execute(query, params).fetchall():
                premium_ids.add(row[0])

        boosted = {}
        for sid, base in scores.items():
            if sid in premium_ids:
                boosted[sid] = float(base) * settings.premium_boost_multiplier
            else:
                boosted[sid] = float(base)
        return boosted

    def _ensure_premium_slots(self, ranked_items: list[tuple[str, float]], limit: int) -> list[tuple[str, float]]:
        if not ranked_items:
            return ranked_items
        ids = [sid for sid, _ in ranked_items]
        placeholders = ",".join([f":id_{i}" for i in range(len(ids))])
        params = {f"id_{i}": sid for i, sid in enumerate(ids)}
        params["premium_type"] = settings.premium_song_type
        query = text(
            f"""
            SELECT id
            FROM song
            WHERE id IN ({placeholders})
              AND type = :premium_type
            """
        )
        premium_ids = set()
        with self.engine.connect() as conn:
            for row in conn.execute(query, params).fetchall():
                premium_ids.add(row[0])

        current_top = ranked_items[:limit]
        current_premium = [x for x in current_top if x[0] in premium_ids]
        need = max(0, settings.premium_min_slots - len(current_premium))
        if need == 0:
            return current_top

        backup = [x for x in ranked_items[limit:] if x[0] in premium_ids][:need]
        if not backup:
            return current_top

        non_premium_top = [x for x in current_top if x[0] not in premium_ids]
        keep_non_premium = non_premium_top[: max(0, limit - len(current_premium) - len(backup))]
        merged = current_premium + backup + keep_non_premium
        merged = sorted(merged, key=lambda x: x[1], reverse=True)
        return merged[:limit]

    def normalize_scores(self, items: list[tuple[str, float]]) -> list[tuple[str, float]]:
        if not items:
            return items
        vals = [float(s) for _, s in items]
        mx = max(vals)
        mn = min(vals)
        if mx == mn:
            return [(sid, 1.0) for sid, _ in items]
        return [(sid, (float(sc) - mn) / (mx - mn)) for sid, sc in items]

    def enrich_items(self, items: list[tuple[str, float]]) -> list[dict]:
        if not items:
            return []
        ids = [sid for sid, _ in items]
        placeholders = ",".join([f":id_{i}" for i in range(len(ids))])
        params = {f"id_{i}": sid for i, sid in enumerate(ids)}
        query = text(
            f"""
            SELECT s.id, s.name, s.language, s.duration, s.thumbnail, s.type,
                   CASE WHEN aq.cnt > 0 THEN 1 ELSE 0 END AS has_audio,
                   COALESCE(aq.cnt, 0) AS audio_quality_count
            FROM song s
            LEFT JOIN (
                SELECT song_id, COUNT(*) AS cnt
                FROM audio_quality
                GROUP BY song_id
            ) aq ON aq.song_id = s.id
            WHERE s.id IN ({placeholders})
            """
        )
        by_id: dict[str, dict] = {}
        with self.engine.connect() as conn:
            for row in conn.execute(query, params).mappings():
                by_id[row["id"]] = {
                    "name": row["name"],
                    "language": row["language"],
                    "duration": float(row["duration"]) if row["duration"] is not None else None,
                    "thumbnail": row["thumbnail"],
                    "has_audio": bool(row["has_audio"]),
                    "audio_quality_count": int(row["audio_quality_count"]),
                    "is_premium": row["type"] == settings.premium_song_type,
                }
        out = []
        for sid, score in items:
            meta = by_id.get(sid, {})
            out.append(
                {
                    "song_id": sid,
                    "score": float(score),
                    "name": meta.get("name"),
                    "language": meta.get("language"),
                    "duration": meta.get("duration"),
                    "thumbnail": meta.get("thumbnail"),
                    "has_audio": meta.get("has_audio"),
                    "audio_quality_count": meta.get("audio_quality_count"),
                    "is_premium": meta.get("is_premium"),
                }
            )
        return out

    def _popular_candidates(self, limit: int, language: str | None = None) -> dict[str, float]:
        language_filter = ""
        params = {"limit": limit}
        if language:
            language_filter = "AND s.language = :language"
            params["language"] = language

        query = text(
            f"""
            SELECT s.id AS song_id,
                   COALESCE(MAX(sr.total_listens), 0) AS rank_score,
                   COALESCE(ic.cnt, 0) AS interaction_score
            FROM song s
            LEFT JOIN song_ranking sr ON sr.song_id = s.id
            LEFT JOIN (
                SELECT song_id, COUNT(*) AS cnt
                FROM interaction_song
                GROUP BY song_id
            ) ic ON ic.song_id = s.id
            WHERE s.deleted_at IS NULL {language_filter}
              AND EXISTS (SELECT 1 FROM audio_quality aq WHERE aq.song_id = s.id)
            GROUP BY s.id, ic.cnt
            ORDER BY (rank_score * 0.7 + interaction_score * 0.3) DESC
            LIMIT :limit
            """
        )
        out: dict[str, float] = {}
        with self.engine.connect() as conn:
            for row in conn.execute(query, params).mappings():
                out[row["song_id"]] = float(row["rank_score"]) * 0.7 + float(row["interaction_score"]) * 0.3
        return out

    def recommend_for_user(self, user_id: str, limit: int, language: str | None = None) -> list[tuple[str, float]]:
        try:
            scores: dict[str, float] = defaultdict(float)
            listened_query = text(
                """
                SELECT song_id, action_type, COUNT(*) AS cnt
                FROM interaction_song
                WHERE user_id = :user_id
                GROUP BY song_id, action_type
                ORDER BY cnt DESC
                LIMIT 80
                """
            )
            user_songs: list[tuple[str, int]] = []
            with self.engine.connect() as conn:
                for row in conn.execute(listened_query, {"user_id": user_id}).mappings():
                    user_songs.append((row["song_id"], row["action_type"]))

            if not user_songs:
                return self._top_n(self._popular_candidates(limit=limit, language=language), limit)

            seed_ids = list(dict.fromkeys([s for s, _ in user_songs]))[:60]
            placeholders = ",".join([f":sid_{i}" for i in range(len(seed_ids))])
            params = {f"sid_{i}": sid for i, sid in enumerate(seed_ids)}

            content_query = text(
                f"""
                SELECT s2.id AS song_id,
                       SUM(CASE WHEN gs2.genre_id IS NOT NULL THEN 1 ELSE 0 END) AS genre_overlap,
                       SUM(CASE WHEN ars2.artist_id IS NOT NULL THEN 1 ELSE 0 END) AS artist_overlap
                FROM song s2
                LEFT JOIN genre_song gs2 ON gs2.song_id = s2.id
                LEFT JOIN artist_song ars2 ON ars2.song_id = s2.id
                WHERE s2.deleted_at IS NULL
                  AND s2.id NOT IN ({placeholders})
                  AND (
                    gs2.genre_id IN (SELECT DISTINCT genre_id FROM genre_song WHERE song_id IN ({placeholders}))
                    OR ars2.artist_id IN (SELECT DISTINCT artist_id FROM artist_song WHERE song_id IN ({placeholders}))
                  )
                GROUP BY s2.id
                ORDER BY (artist_overlap * 2 + genre_overlap) DESC
                LIMIT 500
                """
            )
            with self.engine.connect() as conn:
                for row in conn.execute(content_query, params).mappings():
                    scores[row["song_id"]] += float(row["artist_overlap"]) * 2.0 + float(row["genre_overlap"]) * 1.0

            collab_query = text(
                f"""
                SELECT i2.song_id AS song_id, COUNT(*) AS co_count
                FROM interaction_song i1
                JOIN interaction_song i2 ON i1.user_id = i2.user_id AND i1.song_id <> i2.song_id
                WHERE i1.song_id IN ({placeholders})
                  AND i2.song_id NOT IN ({placeholders})
                GROUP BY i2.song_id
                ORDER BY co_count DESC
                LIMIT 500
                """
            )
            with self.engine.connect() as conn:
                for row in conn.execute(collab_query, params).mappings():
                    scores[row["song_id"]] += float(row["co_count"]) * 1.5

            artist_pref_query = text(
                """
                SELECT artist_id, COALESCE(SUM(interaction_count), 0) AS w
                FROM interaction_artist
                WHERE user_id = :user_id
                GROUP BY artist_id
                ORDER BY w DESC
                LIMIT 30
                """
            )
            top_artists: list[tuple[str, float]] = []
            with self.engine.connect() as conn:
                for row in conn.execute(artist_pref_query, {"user_id": user_id}).mappings():
                    top_artists.append((row["artist_id"], float(row["w"])))

            if top_artists:
                a_ids = [a for a, _ in top_artists]
                a_placeholders = ",".join([f":aid_{i}" for i in range(len(a_ids))])
                a_params = {f"aid_{i}": aid for i, aid in enumerate(a_ids)}
                artist_song_query = text(
                    f"""
                    SELECT song_id, artist_id
                    FROM artist_song
                    WHERE artist_id IN ({a_placeholders})
                    """
                )
                artist_weight = {a: w for a, w in top_artists}
                with self.engine.connect() as conn:
                    for row in conn.execute(artist_song_query, a_params).mappings():
                        sid = row["song_id"]
                        if sid not in seed_ids:
                            scores[sid] += artist_weight.get(row["artist_id"], 0.0) * 0.25

            for song_id, action_type in user_songs:
                scores.pop(song_id, None)
                boost = ACTION_WEIGHT.get(action_type, 1.0)
                for k in list(scores.keys()):
                    scores[k] = scores[k] * (1.0 + 0.02 * boost)

            pop = self._popular_candidates(limit=300, language=language)
            for sid, sc in pop.items():
                scores[sid] += sc * 0.1

            scores = self._apply_language_filter(scores, language)
            scores = self._audio_quality_boost(scores)
            scores = self._premium_boost(scores)
            scores = self._apply_heavy_user_bias(user_id, scores)
            ranked = self._top_n(scores, max(limit * 3, limit))
            ranked = self._ensure_premium_slots(ranked, limit)
            ranked = self._ensure_long_tail_slots_for_heavy(user_id, ranked, limit)
            return ranked
        except Exception:
            return self._top_n(self._popular_candidates(limit=limit, language=language), limit)

    def recommend_similar_song(self, song_id: str, limit: int, language: str | None = None) -> list[tuple[str, float]]:
        scores: dict[str, float] = defaultdict(float)

        content_query = text(
            """
            SELECT s2.id AS song_id,
                   SUM(CASE WHEN gs2.genre_id IN (SELECT genre_id FROM genre_song WHERE song_id = :song_id) THEN 1 ELSE 0 END) AS genre_overlap,
                   SUM(CASE WHEN ars2.artist_id IN (SELECT artist_id FROM artist_song WHERE song_id = :song_id) THEN 1 ELSE 0 END) AS artist_overlap
            FROM song s2
            LEFT JOIN genre_song gs2 ON gs2.song_id = s2.id
            LEFT JOIN artist_song ars2 ON ars2.song_id = s2.id
            WHERE s2.deleted_at IS NULL AND s2.id <> :song_id
            GROUP BY s2.id
            HAVING genre_overlap > 0 OR artist_overlap > 0
            ORDER BY (artist_overlap * 2 + genre_overlap) DESC
            LIMIT 500
            """
        )
        with self.engine.connect() as conn:
            for row in conn.execute(content_query, {"song_id": song_id}).mappings():
                scores[row["song_id"]] += float(row["artist_overlap"]) * 2.0 + float(row["genre_overlap"]) * 1.0

        collab_query = text(
            """
            SELECT i2.song_id AS song_id, COUNT(*) AS co_count
            FROM interaction_song i1
            JOIN interaction_song i2 ON i1.user_id = i2.user_id AND i1.song_id <> i2.song_id
            WHERE i1.song_id = :song_id
            GROUP BY i2.song_id
            ORDER BY co_count DESC
            LIMIT 500
            """
        )
        with self.engine.connect() as conn:
            for row in conn.execute(collab_query, {"song_id": song_id}).mappings():
                scores[row["song_id"]] += float(row["co_count"]) * 1.5

        if not scores:
            return self._top_n(self._popular_candidates(limit=limit, language=language), limit)
        scores = self._apply_language_filter(scores, language)
        scores = self._audio_quality_boost(scores)
        scores = self._premium_boost(scores)
        ranked = self._top_n(scores, max(limit * 3, limit))
        return self._ensure_premium_slots(ranked, limit)

    def recommend_for_playlist(self, user_id: str, seed_song_id: str | None, limit: int, language: str | None = None) -> list[tuple[str, float]]:
        user_scores = dict(self.recommend_for_user(user_id, limit=300, language=language))
        if not seed_song_id:
            return self._top_n(user_scores, limit)
        similar_scores = dict(self.recommend_similar_song(seed_song_id, limit=300, language=language))
        merged: dict[str, float] = defaultdict(float)
        for sid, sc in user_scores.items():
            merged[sid] += sc * 0.6
        for sid, sc in similar_scores.items():
            merged[sid] += sc * 0.4
        merged = self._premium_boost(merged)
        merged = self._apply_heavy_user_bias(user_id, merged)
        ranked = self._top_n(merged, max(limit * 3, limit))
        ranked = self._ensure_premium_slots(ranked, limit)
        ranked = self._ensure_long_tail_slots_for_heavy(user_id, ranked, limit)
        return ranked

    def recommend_for_guest(self, limit: int, language: str | None = None, current_song_id: str | None = None) -> list[tuple[str, float]]:
        base = self._popular_candidates(limit=300, language=language)
        if current_song_id:
            similar = dict(self.recommend_similar_song(current_song_id, limit=300, language=language))
            merged: dict[str, float] = defaultdict(float)
            for sid, sc in base.items():
                merged[sid] += sc * 0.5
            for sid, sc in similar.items():
                merged[sid] += sc * 0.5
            merged = self._audio_quality_boost(merged)
            merged = self._premium_boost(merged)
            ranked = self._top_n(merged, max(limit * 3, limit))
            return self._ensure_premium_slots(ranked, limit)
        base = self._audio_quality_boost(base)
        base = self._premium_boost(base)
        ranked = self._top_n(base, max(limit * 3, limit))
        return self._ensure_premium_slots(ranked, limit)

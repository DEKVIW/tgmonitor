from __future__ import annotations

import json
from typing import Any
from urllib import error, parse, request


TMDB_API_ROOT = "https://api.themoviedb.org/3"
TMDB_POSTER_ROOT = "https://image.tmdb.org/t/p/w342"


class TmdbClient:
    def __init__(
        self,
        *,
        read_access_token: str = "",
        api_key: str = "",
        language: str = "zh-CN",
        timeout_seconds: int = 8,
    ) -> None:
        self.read_access_token = (read_access_token or "").strip()
        self.api_key = (api_key or "").strip()
        self.language = (language or "zh-CN").strip() or "zh-CN"
        self.timeout_seconds = max(3, min(int(timeout_seconds or 8), 30))

    @property
    def is_configured(self) -> bool:
        return bool(self.read_access_token or self.api_key)

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "TGMonitor/1.0",
        }
        if self.read_access_token:
            headers["Authorization"] = f"Bearer {self.read_access_token}"
        return headers

    def _build_url(self, path: str, params: dict[str, Any]) -> str:
        query = dict(params)
        query["language"] = self.language
        query["include_adult"] = "false"
        if self.api_key and not self.read_access_token:
            query["api_key"] = self.api_key
        encoded = parse.urlencode({key: value for key, value in query.items() if value not in (None, "")})
        return f"{TMDB_API_ROOT}{path}?{encoded}"

    def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.is_configured:
            return {}
        url = self._build_url(path, params)
        req = request.Request(url, headers=self._build_headers(), method="GET")
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw_body = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"TMDB request failed with HTTP {exc.code}: {detail or exc.reason}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"TMDB request failed: {exc.reason}") from exc

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("TMDB returned invalid JSON") from exc
        if isinstance(payload, dict):
            return payload
        return {}

    @staticmethod
    def _parse_year(value: Any) -> int | None:
        text = str(value or "").strip()
        if len(text) >= 4 and text[:4].isdigit():
            return int(text[:4])
        return None

    @staticmethod
    def _normalize_media_type(value: Any) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {"movie", "tv"}:
            return normalized
        return "unknown"

    def search(self, *, query: str, year: int | None = None, limit: int = 8) -> list[dict[str, Any]]:
        normalized_query = (query or "").strip()
        if not normalized_query or not self.is_configured:
            return []

        payload = self._get_json(
            "/search/multi",
            {
                "query": normalized_query,
                "page": 1,
            },
        )
        results = payload.get("results")
        if not isinstance(results, list):
            return []

        items: list[dict[str, Any]] = []
        for row in results:
            if not isinstance(row, dict):
                continue
            media_type = self._normalize_media_type(row.get("media_type"))
            if media_type not in {"movie", "tv"}:
                continue

            provider_work_id = row.get("id")
            if provider_work_id in (None, ""):
                continue

            title = str(row.get("title") or row.get("name") or "").strip()
            original_title = str(row.get("original_title") or row.get("original_name") or "").strip()
            release_year = self._parse_year(row.get("release_date") or row.get("first_air_date"))
            if year is not None and release_year is not None and abs(int(year) - int(release_year)) > 15:
                continue

            poster_path = str(row.get("poster_path") or "").strip()
            items.append(
                {
                    "provider": "tmdb",
                    "provider_work_id": str(provider_work_id),
                    "media_type": media_type,
                    "canonical_title": title or original_title or f"TMDB {provider_work_id}",
                    "original_title": original_title or title or None,
                    "release_year": release_year,
                    "poster_url": f"{TMDB_POSTER_ROOT}{poster_path}" if poster_path else None,
                    "detail_url": f"https://www.themoviedb.org/{media_type}/{provider_work_id}",
                    "popularity": float(row.get("popularity") or 0),
                    "aliases": [alias for alias in (title, original_title) if alias],
                    "extra_json": {
                        "language": row.get("original_language"),
                        "overview": row.get("overview"),
                    },
                }
            )

        items.sort(key=lambda item: float(item.get("popularity") or 0), reverse=True)
        return items[: max(1, min(int(limit or 8), 20))]

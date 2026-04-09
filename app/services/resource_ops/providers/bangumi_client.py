from __future__ import annotations

import json
from typing import Any
from urllib import error, parse, request


class BangumiClient:
    def __init__(
        self,
        *,
        user_agent: str = "TGMonitor/1.0",
        timeout_seconds: int = 8,
    ) -> None:
        self.user_agent = (user_agent or "TGMonitor/1.0").strip() or "TGMonitor/1.0"
        self.timeout_seconds = max(3, min(int(timeout_seconds or 8), 30))

    @property
    def is_configured(self) -> bool:
        return bool(self.user_agent)

    @staticmethod
    def _parse_year(value: Any) -> int | None:
        text = str(value or "").strip()
        if len(text) >= 4 and text[:4].isdigit():
            return int(text[:4])
        return None

    def search(self, *, query: str, limit: int = 8) -> list[dict[str, Any]]:
        normalized_query = (query or "").strip()
        if not normalized_query or not self.is_configured:
            return []

        url = (
            "https://api.bgm.tv/search/subject/"
            f"{parse.quote(normalized_query)}?type=2&responseGroup=small"
        )
        req = request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": self.user_agent,
            },
            method="GET",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw_body = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Bangumi request failed with HTTP {exc.code}: {detail or exc.reason}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Bangumi request failed: {exc.reason}") from exc

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Bangumi returned invalid JSON") from exc

        rows = payload.get("list") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return []

        items: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            provider_work_id = row.get("id")
            if provider_work_id in (None, ""):
                continue

            title = str(row.get("name_cn") or "").strip()
            original_title = str(row.get("name") or "").strip()
            images = row.get("images") if isinstance(row.get("images"), dict) else {}
            poster_url = (
                images.get("large")
                or images.get("common")
                or images.get("medium")
                or images.get("small")
            )
            items.append(
                {
                    "provider": "bangumi",
                    "provider_work_id": str(provider_work_id),
                    "media_type": "anime",
                    "canonical_title": title or original_title or f"Bangumi {provider_work_id}",
                    "original_title": original_title or title or None,
                    "release_year": self._parse_year(row.get("air_date") or row.get("date")),
                    "poster_url": poster_url,
                    "detail_url": f"https://bgm.tv/subject/{provider_work_id}",
                    "popularity": float(row.get("score") or 0),
                    "aliases": [alias for alias in (title, original_title) if alias],
                    "extra_json": {
                        "rank": row.get("rank"),
                        "score": row.get("score"),
                        "summary": row.get("summary"),
                    },
                }
            )

        items.sort(key=lambda item: float(item.get("popularity") or 0), reverse=True)
        return items[: max(1, min(int(limit or 8), 20))]

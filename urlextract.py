"""Small local fallback for environments without the external urlextract package."""

from __future__ import annotations

import re
from typing import List


class URLExtract:
    _pattern = re.compile(r"(?:https?://|www\.)[^\s\"'<>]+", re.IGNORECASE)

    def find_urls(self, text: str) -> List[str]:
        return self._pattern.findall(text or "")

    def has_urls(self, text: str) -> bool:
        return bool(self._pattern.search(text or ""))

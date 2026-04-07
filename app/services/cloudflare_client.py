from __future__ import annotations

import json
from typing import Any
from urllib import error, request


CLOUDFLARE_API_BASE_URL = "https://api.cloudflare.com/client/v4"


class CloudflareApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, errors: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.errors = errors or []


class CloudflareApiNotFoundError(CloudflareApiError):
    pass


class CloudflareClient:
    def __init__(self, api_token: str):
        normalized_token = (api_token or "").strip()
        if not normalized_token:
            raise ValueError("Cloudflare API token is required")
        self.api_token = normalized_token

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")

        req = request.Request(f"{CLOUDFLARE_API_BASE_URL}{path}", data=data, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=15) as response:
                raw_body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            raw_body = exc.read().decode("utf-8")
            try:
                parsed = json.loads(raw_body)
            except Exception:
                parsed = {}
            errors = parsed.get("errors") if isinstance(parsed, dict) else None
            message = parsed.get("message") if isinstance(parsed, dict) else None
            if not message and isinstance(errors, list) and errors:
                message = "; ".join(str(item.get("message") or item.get("code") or "Cloudflare API error") for item in errors)
            message = message or f"Cloudflare API request failed with status {exc.code}"
            error_cls = CloudflareApiNotFoundError if exc.code == 404 else CloudflareApiError
            raise error_cls(message, status_code=exc.code, errors=errors if isinstance(errors, list) else None) from exc
        except error.URLError as exc:
            raise CloudflareApiError(f"Cloudflare API request failed: {exc.reason}") from exc

        try:
            parsed = json.loads(raw_body)
        except Exception as exc:
            raise CloudflareApiError("Cloudflare API returned invalid JSON") from exc

        if not isinstance(parsed, dict):
            raise CloudflareApiError("Cloudflare API returned an unexpected response")
        if not parsed.get("success"):
            errors = parsed.get("errors")
            message = parsed.get("message")
            if not message and isinstance(errors, list) and errors:
                message = "; ".join(str(item.get("message") or item.get("code") or "Cloudflare API error") for item in errors)
            raise CloudflareApiError(message or "Cloudflare API request failed", errors=errors if isinstance(errors, list) else None)
        return parsed.get("result") or {}

    def get_phase_entrypoint_ruleset(self, zone_id: str, phase: str) -> dict[str, Any]:
        return self._request("GET", f"/zones/{zone_id}/rulesets/phases/{phase}/entrypoint")

    def create_phase_entrypoint_ruleset(self, zone_id: str, phase: str, *, rules: list[dict[str, Any]]) -> dict[str, Any]:
        payload = {
            "description": "TG Monitor managed Cloudflare security rules",
            "rules": rules,
        }
        return self._request("PUT", f"/zones/{zone_id}/rulesets/phases/{phase}/entrypoint", payload)

    def create_rule(self, zone_id: str, ruleset_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/zones/{zone_id}/rulesets/{ruleset_id}/rules", payload)

    def update_rule(self, zone_id: str, ruleset_id: str, rule_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", f"/zones/{zone_id}/rulesets/{ruleset_id}/rules/{rule_id}", payload)

    def delete_rule(self, zone_id: str, ruleset_id: str, rule_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/zones/{zone_id}/rulesets/{ruleset_id}/rules/{rule_id}")

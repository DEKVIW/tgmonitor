from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.services.resource_ops.settings import resolve_resource_ops_ai_request_config


AI_RECOGNITION_SYSTEM_PROMPT = """
你是影视剧名称提取助手。
用户会给你一段原始消息标题。
你的任务只有一个：提取这段文字里的影视剧名称。
只回复影视剧名称本身，不要解释，不要加前缀，不要加标点，不要返回 JSON，不要返回多行。
如果无法判断，就回复空字符串。
""".strip()

TITLE_PREFIX_PATTERN = re.compile(r"^(影视剧名称|剧名|名称|标题|答案)\s*[:：]\s*", re.IGNORECASE)


class ResourceOpsAiError(RuntimeError):
    pass


@dataclass(slots=True)
class ResourceOpsAiRecognitionResult:
    title: str
    original_title: str | None = None
    aliases: list[str] = field(default_factory=list)
    year: int | None = None
    season: int | None = None
    media_type: str | None = None
    confidence: float = 0.0
    reason: str = ""
    raw_content: str = ""
    used_model: str = ""


def _normalize_text(value: Any, *, max_length: int | None = None) -> str:
    text = "" if value is None else str(value).strip()
    if max_length is not None and len(text) > max_length:
        text = text[:max_length].strip()
    return text


def _normalize_base_url(base_url: str) -> str:
    normalized = _normalize_text(base_url, max_length=512).rstrip("/")
    if not normalized:
        return ""
    if not normalized.lower().endswith("/v1"):
        normalized = f"{normalized}/v1"
    return normalized


def _extract_plain_title(raw_text: str) -> str:
    normalized = raw_text.strip()
    if not normalized:
        raise ResourceOpsAiError("AI 返回了空内容")

    try:
        parsed = json.loads(normalized)
        if isinstance(parsed, dict):
            title = _normalize_text(parsed.get("title"), max_length=255)
            if title:
                return title
    except json.JSONDecodeError:
        pass

    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    title = lines[0] if lines else normalized
    title = title.replace("```", "").strip()
    title = TITLE_PREFIX_PATTERN.sub("", title).strip()
    title = title.strip("`'\"“”‘’[](){}<>")
    if title.startswith("《") and title.endswith("》") and len(title) > 2:
        title = title[1:-1].strip()
    return _normalize_text(title, max_length=255)


def _http_request_json(
    method: str,
    url: str,
    *,
    api_key: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 18,
) -> dict[str, Any]:
    data = None
    headers = {
        "Accept": "application/json",
        "User-Agent": "TGMonitor/1.0",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url=url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            body = response.read().decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        raw_body = exc.read().decode("utf-8", errors="replace")
        detail = raw_body
        try:
            parsed = json.loads(raw_body)
            detail = (
                _normalize_text(parsed.get("error", {}).get("message"))
                or _normalize_text(parsed.get("message"))
                or raw_body
            )
        except Exception:
            detail = raw_body or str(exc)
        raise ResourceOpsAiError(f"AI 请求失败: {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise ResourceOpsAiError(f"AI 连接失败: {exc.reason}") from exc

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ResourceOpsAiError("AI 接口返回了非 JSON 数据") from exc
    if not isinstance(parsed, dict):
        raise ResourceOpsAiError("AI 接口返回格式不正确")
    return parsed


def _extract_completion_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if isinstance(item, dict):
                        if isinstance(item.get("text"), str):
                            parts.append(item["text"])
                        elif item.get("type") == "text" and isinstance(item.get("value"), str):
                            parts.append(item["value"])
                if parts:
                    return "\n".join(parts)
    raise ResourceOpsAiError("AI 没有返回可解析的文本内容")


def _build_user_prompt(*, primary_title: str) -> str:
    normalized_title = _normalize_text(primary_title, max_length=500)
    return f"{normalized_title}\n\n把这段文字的影视剧名称提取处理，只要影视剧名称，不要多回答。"


def _extract_model_ids(payload: dict[str, Any]) -> list[str]:
    data = payload.get("data")
    model_ids: list[str] = []
    seen: set[str] = set()
    if isinstance(data, list):
        for row in data:
            if not isinstance(row, dict):
                continue
            model_id = _normalize_text(row.get("id"), max_length=255)
            if not model_id or model_id in seen:
                continue
            seen.add(model_id)
            model_ids.append(model_id)
    return model_ids


def _load_available_model_ids(*, base_url: str, api_key: str) -> list[str]:
    response = _http_request_json("GET", f"{base_url}/models", api_key=api_key)
    return _extract_model_ids(response)


def _should_retry_with_fallback_model(exc: ResourceOpsAiError) -> bool:
    detail = str(exc).lower()
    return "model" in detail and any(
        token in detail
        for token in ("not found", "does not exist", "invalid", "unsupported", "no such", "不存在", "模型")
    )


def list_resource_ops_ai_models(session: Session, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    request_config = resolve_resource_ops_ai_request_config(session, payload)
    base_url = _normalize_base_url(str(request_config.get("base_url") or ""))
    api_key = _normalize_text(request_config.get("api_key"), max_length=8000)
    if not base_url:
        raise ResourceOpsAiError("请先填写 AI Base URL")
    if not api_key:
        raise ResourceOpsAiError("请先填写 AI API Key")

    response = _http_request_json("GET", f"{base_url}/models", api_key=api_key)
    items: list[dict[str, str]] = []
    for model_id in _extract_model_ids(response):
        items.append(
            {
                "id": model_id,
                "label": model_id,
                "owned_by": "",
            }
        )

    return {
        "models": items,
        "base_url": base_url,
        "used_saved_api_key": bool(request_config.get("used_saved_api_key")),
        "count": len(items),
    }


def recognize_resource_with_ai(
    *,
    base_url: str,
    api_key: str,
    model: str,
    primary_title: str,
) -> ResourceOpsAiRecognitionResult:
    normalized_base_url = _normalize_base_url(base_url)
    normalized_api_key = _normalize_text(api_key, max_length=8000)
    normalized_model = _normalize_text(model, max_length=255)
    if not normalized_base_url:
        raise ResourceOpsAiError("AI Base URL 不能为空")
    if not normalized_api_key:
        raise ResourceOpsAiError("AI API Key 不能为空")

    models_to_try: list[str] = [normalized_model] if normalized_model else []
    if not models_to_try:
        models_to_try = _load_available_model_ids(base_url=normalized_base_url, api_key=normalized_api_key)
        if not models_to_try:
            raise ResourceOpsAiError("未获取到可用 AI 模型")

    attempted: set[str] = set()
    last_error: ResourceOpsAiError | None = None

    while models_to_try:
        current_model = models_to_try.pop(0)
        if not current_model or current_model in attempted:
            continue
        attempted.add(current_model)
        try:
            response = _http_request_json(
                "POST",
                f"{normalized_base_url}/chat/completions",
                api_key=normalized_api_key,
                payload={
                    "model": current_model,
                    "temperature": 0,
                    "messages": [
                        {"role": "system", "content": AI_RECOGNITION_SYSTEM_PROMPT},
                        {"role": "user", "content": _build_user_prompt(primary_title=primary_title)},
                    ],
                },
            )
            raw_content = _extract_completion_text(response)
            title = _extract_plain_title(raw_content)
            return ResourceOpsAiRecognitionResult(
                title=title,
                confidence=1.0 if title else 0.0,
                reason="plain_title_extract" if title else "empty_title",
                raw_content=raw_content,
                used_model=current_model,
            )
        except ResourceOpsAiError as exc:
            last_error = exc
            if current_model == normalized_model and _should_retry_with_fallback_model(exc):
                fallback_models = _load_available_model_ids(base_url=normalized_base_url, api_key=normalized_api_key)
                for fallback_model in fallback_models:
                    if fallback_model not in attempted and fallback_model not in models_to_try:
                        models_to_try.append(fallback_model)
                continue
            raise

    if last_error is not None:
        raise last_error
    raise ResourceOpsAiError("AI 识别失败")


def test_resource_ops_ai_connection(session: Session, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    request_payload = payload or {}
    request_config = resolve_resource_ops_ai_request_config(session, request_payload)
    sample_text = _normalize_text(
        request_payload.get("sample_text"),
        max_length=500,
    ) or "月鳞绮纪 2026 第17集 无字幕 鞠婧祎 曾舜晞 陈都灵"
    result = recognize_resource_with_ai(
        base_url=str(request_config.get("base_url") or ""),
        api_key=str(request_config.get("api_key") or ""),
        model=_normalize_text(request_payload.get("model") or request_config.get("model"), max_length=255),
        primary_title=sample_text,
    )
    return {
        "ok": True,
        "base_url": _normalize_base_url(str(request_config.get("base_url") or "")),
        "model": result.used_model or _normalize_text(request_payload.get("model") or request_config.get("model"), max_length=255),
        "sample_text": sample_text,
        "extracted_title": result.title or None,
        "release_year": None,
        "season": None,
        "media_type": None,
        "confidence": result.confidence,
        "reason": result.reason,
    }

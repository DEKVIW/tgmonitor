from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.services.ai_center import execute_text_route
from app.services.resource_ops.settings import RESOURCE_OPS_AI_API_MODES, resolve_resource_ops_ai_request_config


logger = logging.getLogger(__name__)

AI_API_MODE_AUTO = "auto"
AI_API_MODE_CHAT_COMPLETIONS = "chat_completions"
AI_API_MODE_RESPONSES = "responses"
AI_RUNTIME_MODE_CHAT_STREAM = "chat_completions_stream"


AI_RECOGNITION_SYSTEM_PROMPT = """
你是影视剧名称提取助手。
用户会给你一段原始消息标题。
你的任务只有一个：提取这段文字里的影视剧名称本身。
只回复影视剧名称，不要解释，不要加前缀，不要加标点，不要返回 JSON，不要返回多行。
不要输出季数、部数、集数、年份、字幕、画质、演员名字、更新状态、合集说明。
如果原文是“月鳞绮纪 2026 第17集 无字幕 鞠婧祎 曾舜晞 陈都灵”，你只能回复“月鳞绮纪”。
如果无法判断，就回复空字符串。
""".strip()

TITLE_PREFIX_PATTERN = re.compile(r"^(影视剧名称|剧名|名称|标题|答案)\s*[:：]\s*", re.IGNORECASE)
TITLE_SEASON_SUFFIX_PATTERN = re.compile(
    r"\s*(?:"
    r"第\s*[0-9一二三四五六七八九十百零两]+\s*(?:季|部|篇|章)"
    r"|Season\s*\d+"
    r"|S\s*\d{1,2}"
    r"|S\d{1,2}"
    r")\s*$",
    re.IGNORECASE,
)
TITLE_EPISODE_SUFFIX_PATTERN = re.compile(
    r"\s*(?:"
    r"第\s*\d+\s*(?:集|话|期)"
    r"|EP?\s*\d+"
    r"|E\d+"
    r")\s*$",
    re.IGNORECASE,
)
TITLE_NOISE_SUFFIX_PATTERNS = (
    TITLE_SEASON_SUFFIX_PATTERN,
    TITLE_EPISODE_SUFFIX_PATTERN,
    re.compile(r"\s*(?:全集|完结|完整版|无字幕|中字|双语|国语|粤语|4K|8K|2160P|1080P|720P|HDR|杜比视界)\s*$", re.IGNORECASE),
    re.compile(r"\s*(?:\||｜|/|·|-|_)+\s*$", re.IGNORECASE),
)
GENERIC_EMPTY_TITLES = {"影视剧名称", "剧名", "名称", "标题", "答案", "未知", "无"}


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
    used_api_mode: str = ""


@dataclass(slots=True)
class ResourceOpsAiAttempt:
    api_mode: str
    endpoint_path: str
    stream: bool = False

    @property
    def runtime_mode(self) -> str:
        if self.api_mode == AI_API_MODE_CHAT_COMPLETIONS and self.stream:
            return AI_RUNTIME_MODE_CHAT_STREAM
        return self.api_mode


def _normalize_text(value: Any, *, max_length: int | None = None) -> str:
    text = "" if value is None else str(value).strip()
    if max_length is not None and len(text) > max_length:
        text = text[:max_length].strip()
    return text


def _normalize_api_mode(value: Any, default: str = AI_API_MODE_AUTO) -> str:
    normalized = _normalize_text(value, max_length=32).lower() or default
    if normalized not in RESOURCE_OPS_AI_API_MODES:
        return default
    return normalized


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
    title = re.sub(r"\s+", " ", title).strip()

    previous = None
    while title and title != previous:
        previous = title
        for pattern in TITLE_NOISE_SUFFIX_PATTERNS:
            title = pattern.sub("", title).strip()
        title = title.strip("`'\"“”‘’[](){}<>|｜/·-_ ").strip()

    if title in GENERIC_EMPTY_TITLES:
        return ""
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


def _http_request_sse(
    url: str,
    *,
    api_key: str,
    payload: dict[str, Any],
    timeout: int = 30,
) -> list[str]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
        "User-Agent": "TGMonitor/1.0",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    request = urllib.request.Request(url=url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            chunks: list[str] = []
            current_lines: list[str] = []
            for raw_line in response:
                line = raw_line.decode(charset, errors="replace").rstrip("\r\n")
                if not line:
                    if current_lines:
                        chunk = _extract_sse_data_block(current_lines)
                        if chunk is not None:
                            chunks.append(chunk)
                        current_lines = []
                    continue
                if line.startswith(":"):
                    continue
                current_lines.append(line)
            if current_lines:
                chunk = _extract_sse_data_block(current_lines)
                if chunk is not None:
                    chunks.append(chunk)
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
    return chunks


def _merge_text_parts(parts: list[str]) -> str:
    normalized_parts = [_normalize_text(part) for part in parts if _normalize_text(part)]
    return "\n".join(normalized_parts).strip()


def _extract_sse_data_block(lines: list[str]) -> str | None:
    data_lines: list[str] = []
    for line in lines:
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if not data_lines:
        return None
    return "\n".join(data_lines).strip()


def _extract_choice_metadata(choice: dict[str, Any]) -> dict[str, str]:
    finish_reason = _normalize_text(choice.get("finish_reason"), max_length=64) or "-"
    native_finish_reason = _normalize_text(choice.get("native_finish_reason"), max_length=64) or "-"
    return {
        "finish_reason": finish_reason,
        "native_finish_reason": native_finish_reason,
    }


def _truncate_preview_text(value: str, *, max_length: int = 160) -> str:
    text = _normalize_text(value)
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3].rstrip()}..."


def _build_payload_debug_preview(payload: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        if isinstance(payload, (dict, list)):
            return "..."
        if isinstance(payload, str):
            return _truncate_preview_text(payload)
        return payload

    if isinstance(payload, dict):
        preview: dict[str, Any] = {}
        for index, (key, value) in enumerate(payload.items()):
            if index >= 8:
                preview["..."] = f"+{len(payload) - 8} more keys"
                break
            preview[str(key)] = _build_payload_debug_preview(value, depth=depth + 1)
        return preview

    if isinstance(payload, list):
        items = [_build_payload_debug_preview(item, depth=depth + 1) for item in payload[:3]]
        if len(payload) > 3:
            items.append(f"... +{len(payload) - 3} more items")
        return items

    if isinstance(payload, str):
        return _truncate_preview_text(payload)

    return payload


def _format_payload_debug_preview(payload: dict[str, Any]) -> str:
    try:
        preview = _build_payload_debug_preview(payload)
        return json.dumps(preview, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return _truncate_preview_text(repr(payload), max_length=400)


def _extract_text_from_block(value: Any) -> str:
    if isinstance(value, str):
        return _normalize_text(value)

    if isinstance(value, dict):
        for key in ("output_text", "text", "value"):
            raw_text = value.get(key)
            if isinstance(raw_text, str):
                text = _normalize_text(raw_text)
                if text:
                    return text
            text = _extract_text_from_block(raw_text)
            if text:
                return text
        for key in ("message", "content", "parts", "data"):
            text = _extract_text_from_block(value.get(key))
            if text:
                return text
        return ""

    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            text = _extract_text_from_block(item)
            if text:
                parts.append(text)
        return _merge_text_parts(parts)

    return ""


def _extract_completion_text(payload: dict[str, Any]) -> str:
    direct_output_text = _extract_text_from_block(payload.get("output_text"))
    if direct_output_text:
        return direct_output_text

    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first_choice = choices[0] if isinstance(choices[0], dict) else None
        if isinstance(first_choice, dict):
            for key in ("message", "text", "content"):
                text = _extract_text_from_block(first_choice.get(key))
                if text:
                    return text
            message = first_choice.get("message")
            if isinstance(message, dict):
                metadata = _extract_choice_metadata(first_choice)
                preview = _format_payload_debug_preview(first_choice)
                raise ResourceOpsAiError(
                    "AI 返回了空消息，"
                    f"finish_reason={metadata['finish_reason']}，"
                    f"native_finish_reason={metadata['native_finish_reason']}，"
                    f"choice 预览: {preview}"
                )

    response_text = _extract_text_from_block(payload.get("response"))
    if response_text:
        return response_text

    output_text = _extract_text_from_block(payload.get("output"))
    if output_text:
        return output_text

    content_text = _extract_text_from_block(payload.get("content"))
    if content_text:
        return content_text

    candidates = payload.get("candidates")
    if isinstance(candidates, list) and candidates:
        candidate_text = _extract_text_from_block(candidates[0])
        if candidate_text:
            return candidate_text

    for key in ("message", "text"):
        text = _extract_text_from_block(payload.get(key))
        if text:
            return text

    preview = _format_payload_debug_preview(payload)
    logger.warning("AI response did not contain recognizable text payload=%s", preview)
    raise ResourceOpsAiError(f"AI 没有返回可解析的文本内容，响应预览: {preview}")


def _extract_chat_stream_event_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first_choice = choices[0] if isinstance(choices[0], dict) else None
    if not isinstance(first_choice, dict):
        return ""
    delta = first_choice.get("delta")
    if isinstance(delta, dict):
        for key in ("content", "text"):
            text = _extract_text_from_block(delta.get(key))
            if text:
                return text
    for key in ("message", "content", "text"):
        text = _extract_text_from_block(first_choice.get(key))
        if text:
            return text
    return ""


def _extract_responses_stream_event_text(payload: dict[str, Any]) -> str:
    event_type = _normalize_text(payload.get("type"), max_length=128)
    if event_type in {"response.output_text.delta", "response.output_text.done"}:
        return _normalize_text(payload.get("delta") or payload.get("text"))
    if event_type.startswith("response.") and "output_text" in event_type:
        return _extract_text_from_block(payload)
    return _extract_text_from_block(payload)


def _extract_stream_text(chunks: list[str], *, api_mode: str) -> str:
    parts: list[str] = []
    last_payload: dict[str, Any] | None = None
    for chunk in chunks:
        if not chunk or chunk == "[DONE]":
            continue
        try:
            payload = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        last_payload = payload
        if api_mode == AI_API_MODE_RESPONSES:
            text = _extract_responses_stream_event_text(payload)
        else:
            text = _extract_chat_stream_event_text(payload)
        if text:
            parts.append(text)
    merged = "".join(parts).strip()
    if merged:
        return merged
    if last_payload is not None:
        preview = _format_payload_debug_preview(last_payload)
        raise ResourceOpsAiError(f"AI 流式响应未返回正文，事件预览: {preview}")
    raise ResourceOpsAiError("AI 流式响应为空")


def _build_user_prompt(*, primary_title: str) -> str:
    normalized_title = _normalize_text(primary_title, max_length=500)
    return (
        f"{normalized_title}\n\n"
        "把这段文字里的影视剧名称提取出来，只返回影视剧名称本身。"
        "不要返回第几季、多少集、年份、字幕、画质、演员、更新状态，也不要多说一句话。"
    )


def _build_chat_messages(*, primary_title: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": AI_RECOGNITION_SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(primary_title=primary_title)},
    ]


def _build_chat_completion_payload(*, model: str, primary_title: str, stream: bool) -> dict[str, Any]:
    return {
        "model": model,
        "temperature": 0,
        "stream": stream,
        "messages": _build_chat_messages(primary_title=primary_title),
    }


def _build_responses_payload(*, model: str, primary_title: str) -> dict[str, Any]:
    return {
        "model": model,
        "temperature": 0,
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": AI_RECOGNITION_SYSTEM_PROMPT,
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": _build_user_prompt(primary_title=primary_title),
                    }
                ],
            },
        ],
    }


def _build_attempt_plan(api_mode: str) -> list[ResourceOpsAiAttempt]:
    normalized_mode = _normalize_api_mode(api_mode)
    if normalized_mode == AI_API_MODE_CHAT_COMPLETIONS:
        return [
            ResourceOpsAiAttempt(api_mode=AI_API_MODE_CHAT_COMPLETIONS, endpoint_path="/chat/completions", stream=False),
            ResourceOpsAiAttempt(api_mode=AI_API_MODE_CHAT_COMPLETIONS, endpoint_path="/chat/completions", stream=True),
        ]
    if normalized_mode == AI_API_MODE_RESPONSES:
        return [
            ResourceOpsAiAttempt(api_mode=AI_API_MODE_RESPONSES, endpoint_path="/responses", stream=False),
        ]
    return [
        ResourceOpsAiAttempt(api_mode=AI_API_MODE_CHAT_COMPLETIONS, endpoint_path="/chat/completions", stream=False),
        ResourceOpsAiAttempt(api_mode=AI_API_MODE_CHAT_COMPLETIONS, endpoint_path="/chat/completions", stream=True),
        ResourceOpsAiAttempt(api_mode=AI_API_MODE_RESPONSES, endpoint_path="/responses", stream=False),
    ]


def _execute_ai_attempt(
    *,
    base_url: str,
    api_key: str,
    model: str,
    primary_title: str,
    attempt: ResourceOpsAiAttempt,
) -> str:
    if attempt.api_mode == AI_API_MODE_RESPONSES:
        payload = _build_responses_payload(model=model, primary_title=primary_title)
    else:
        payload = _build_chat_completion_payload(model=model, primary_title=primary_title, stream=attempt.stream)

    endpoint_url = f"{base_url}{attempt.endpoint_path}"
    if attempt.stream:
        chunks = _http_request_sse(endpoint_url, api_key=api_key, payload=payload)
        return _extract_stream_text(chunks, api_mode=attempt.api_mode)

    response = _http_request_json("POST", endpoint_url, api_key=api_key, payload=payload)
    return _extract_completion_text(response)


def _summarize_attempt_errors(errors: list[tuple[str, str]]) -> ResourceOpsAiError:
    if not errors:
        return ResourceOpsAiError("AI 识别失败")
    if len(errors) == 1:
        return ResourceOpsAiError(errors[0][1])
    summary = "；".join(
        f"{label}: {_truncate_preview_text(detail, max_length=220)}"
        for label, detail in errors
    )
    return ResourceOpsAiError(summary)


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
    ai_api_mode: str = AI_API_MODE_AUTO,
    primary_title: str,
) -> ResourceOpsAiRecognitionResult:
    normalized_base_url = _normalize_base_url(base_url)
    normalized_api_key = _normalize_text(api_key, max_length=8000)
    normalized_api_mode = _normalize_api_mode(ai_api_mode, AI_API_MODE_AUTO)
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
        attempt_errors: list[tuple[str, str]] = []
        should_retry_models = False

        for attempt in _build_attempt_plan(normalized_api_mode):
            try:
                raw_content = _execute_ai_attempt(
                    base_url=normalized_base_url,
                    api_key=normalized_api_key,
                    model=current_model,
                    primary_title=primary_title,
                    attempt=attempt,
                )
                title = _extract_plain_title(raw_content)
                return ResourceOpsAiRecognitionResult(
                    title=title,
                    confidence=1.0 if title else 0.0,
                    reason="plain_title_extract" if title else "empty_title",
                    raw_content=raw_content,
                    used_model=current_model,
                    used_api_mode=attempt.runtime_mode,
                )
            except ResourceOpsAiError as exc:
                detail = str(exc)
                attempt_errors.append((attempt.runtime_mode, detail))
                if current_model == normalized_model and _should_retry_with_fallback_model(exc):
                    fallback_models = _load_available_model_ids(base_url=normalized_base_url, api_key=normalized_api_key)
                    for fallback_model in fallback_models:
                        if fallback_model not in attempted and fallback_model not in models_to_try:
                            models_to_try.append(fallback_model)
                    should_retry_models = True
                    break

        if should_retry_models:
            continue

        last_error = _summarize_attempt_errors(attempt_errors)
        if normalized_model:
            raise last_error

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
        ai_api_mode=_normalize_api_mode(request_payload.get("ai_api_mode") or request_config.get("ai_api_mode"), AI_API_MODE_AUTO),
        primary_title=sample_text,
    )
    return {
        "ok": True,
        "base_url": _normalize_base_url(str(request_config.get("base_url") or "")),
        "model": result.used_model or _normalize_text(request_payload.get("model") or request_config.get("model"), max_length=255),
        "used_api_mode": result.used_api_mode or _normalize_api_mode(request_payload.get("ai_api_mode") or request_config.get("ai_api_mode"), AI_API_MODE_AUTO),
        "sample_text": sample_text,
        "extracted_title": result.title or None,
        "release_year": None,
        "season": None,
        "media_type": None,
        "confidence": result.confidence,
        "reason": result.reason,
    }


def recognize_resource_with_ai_center(
    session: Session,
    *,
    primary_title: str,
) -> ResourceOpsAiRecognitionResult:
    route_result = execute_text_route(
        session,
        route_key="resource_ops_title_extract",
        system_prompt=AI_RECOGNITION_SYSTEM_PROMPT,
        user_prompt=_build_user_prompt(primary_title=primary_title),
        metadata={
            "source": "resource_ops",
            "primary_title": _normalize_text(primary_title, max_length=255),
        },
    )
    title = _extract_plain_title(route_result.text)
    return ResourceOpsAiRecognitionResult(
        title=title,
        confidence=1.0 if title else 0.0,
        reason="plain_title_extract" if title else "empty_title",
        raw_content=route_result.text,
        used_model=route_result.model_id or "",
        used_api_mode=route_result.used_api_mode or "",
    )

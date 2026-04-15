from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


logger = logging.getLogger(__name__)

AI_API_MODE_AUTO = "auto"
AI_API_MODE_CHAT_COMPLETIONS = "chat_completions"
AI_API_MODE_RESPONSES = "responses"
AI_RUNTIME_MODE_CHAT_STREAM = "chat_completions_stream"
AI_SUPPORTED_API_MODES = {
    AI_API_MODE_AUTO,
    AI_API_MODE_CHAT_COMPLETIONS,
    AI_API_MODE_RESPONSES,
}


class AiCenterError(RuntimeError):
    pass


@dataclass(slots=True)
class AiTextCompletionResult:
    text: str
    used_model: str
    used_api_mode: str
    raw_content: str


@dataclass(slots=True)
class _AiAttempt:
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


def normalize_base_url(base_url: str) -> str:
    normalized = _normalize_text(base_url, max_length=512).rstrip("/")
    if not normalized:
        return ""
    if not normalized.lower().endswith("/v1"):
        normalized = f"{normalized}/v1"
    return normalized


def normalize_api_mode(value: Any, default: str = AI_API_MODE_AUTO) -> str:
    normalized = _normalize_text(value, max_length=32).lower() or default
    if normalized not in AI_SUPPORTED_API_MODES:
        return default
    return normalized


def _truncate_preview_text(value: str, *, max_length: int = 180) -> str:
    text = _normalize_text(value)
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3].rstrip()}..."


def _build_payload_preview(payload: Any, *, depth: int = 0) -> Any:
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
            preview[str(key)] = _build_payload_preview(value, depth=depth + 1)
        return preview

    if isinstance(payload, list):
        items = [_build_payload_preview(item, depth=depth + 1) for item in payload[:3]]
        if len(payload) > 3:
            items.append(f"... +{len(payload) - 3} more items")
        return items

    if isinstance(payload, str):
        return _truncate_preview_text(payload)

    return payload


def _format_payload_preview(payload: dict[str, Any]) -> str:
    try:
        return json.dumps(_build_payload_preview(payload), ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return _truncate_preview_text(repr(payload), max_length=400)


def _http_request_json(
    method: str,
    url: str,
    *,
    api_key: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 25,
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
        raise AiCenterError(f"AI request failed: {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise AiCenterError(f"AI connection failed: {exc.reason}") from exc

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise AiCenterError("AI endpoint returned non-JSON content") from exc
    if not isinstance(parsed, dict):
        raise AiCenterError("AI endpoint returned an invalid payload")
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
        raise AiCenterError(f"AI request failed: {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise AiCenterError(f"AI connection failed: {exc.reason}") from exc
    return chunks


def _extract_sse_data_block(lines: list[str]) -> str | None:
    data_lines: list[str] = []
    for line in lines:
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if not data_lines:
        return None
    return "\n".join(data_lines).strip()


def _merge_text_parts(parts: list[str]) -> str:
    normalized_parts = [_normalize_text(part) for part in parts if _normalize_text(part)]
    return "\n".join(normalized_parts).strip()


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


def _extract_choice_metadata(choice: dict[str, Any]) -> dict[str, str]:
    return {
        "finish_reason": _normalize_text(choice.get("finish_reason"), max_length=64) or "-",
        "native_finish_reason": _normalize_text(choice.get("native_finish_reason"), max_length=64) or "-",
    }


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
            if isinstance(first_choice.get("message"), dict):
                metadata = _extract_choice_metadata(first_choice)
                preview = _format_payload_preview(first_choice)
                raise AiCenterError(
                    "AI returned an empty message, "
                    f"finish_reason={metadata['finish_reason']}, "
                    f"native_finish_reason={metadata['native_finish_reason']}, "
                    f"choice preview: {preview}"
                )

    for key in ("response", "output", "content", "message", "text"):
        text = _extract_text_from_block(payload.get(key))
        if text:
            return text

    candidates = payload.get("candidates")
    if isinstance(candidates, list) and candidates:
        candidate_text = _extract_text_from_block(candidates[0])
        if candidate_text:
            return candidate_text

    preview = _format_payload_preview(payload)
    logger.warning("AI response did not contain recognizable text payload=%s", preview)
    raise AiCenterError(f"AI response did not contain recognizable text: {preview}")


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
        preview = _format_payload_preview(last_payload)
        raise AiCenterError(f"AI stream returned no content: {preview}")
    raise AiCenterError("AI stream returned no content")


def _build_chat_messages(*, system_prompt: str, user_prompt: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _build_chat_completion_payload(
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    stream: bool,
) -> dict[str, Any]:
    return {
        "model": model,
        "temperature": 0,
        "stream": stream,
        "messages": _build_chat_messages(system_prompt=system_prompt, user_prompt=user_prompt),
    }


def _build_responses_payload(*, model: str, system_prompt: str, user_prompt: str) -> dict[str, Any]:
    return {
        "model": model,
        "temperature": 0,
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": system_prompt,
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": user_prompt,
                    }
                ],
            },
        ],
    }


def _build_attempt_plan(api_mode: str) -> list[_AiAttempt]:
    normalized_mode = normalize_api_mode(api_mode)
    if normalized_mode == AI_API_MODE_CHAT_COMPLETIONS:
        return [
            _AiAttempt(api_mode=AI_API_MODE_CHAT_COMPLETIONS, endpoint_path="/chat/completions", stream=False),
            _AiAttempt(api_mode=AI_API_MODE_CHAT_COMPLETIONS, endpoint_path="/chat/completions", stream=True),
        ]
    if normalized_mode == AI_API_MODE_RESPONSES:
        return [
            _AiAttempt(api_mode=AI_API_MODE_RESPONSES, endpoint_path="/responses", stream=False),
        ]
    return [
        _AiAttempt(api_mode=AI_API_MODE_CHAT_COMPLETIONS, endpoint_path="/chat/completions", stream=False),
        _AiAttempt(api_mode=AI_API_MODE_CHAT_COMPLETIONS, endpoint_path="/chat/completions", stream=True),
        _AiAttempt(api_mode=AI_API_MODE_RESPONSES, endpoint_path="/responses", stream=False),
    ]


def list_openai_compatible_models(*, base_url: str, api_key: str, timeout_seconds: int = 20) -> list[dict[str, str]]:
    normalized_base_url = normalize_base_url(base_url)
    normalized_api_key = _normalize_text(api_key, max_length=8000)
    if not normalized_base_url:
        raise AiCenterError("AI Base URL cannot be empty")
    if not normalized_api_key:
        raise AiCenterError("AI API Key cannot be empty")

    response = _http_request_json("GET", f"{normalized_base_url}/models", api_key=normalized_api_key, timeout=timeout_seconds)
    data = response.get("data")
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    if isinstance(data, list):
        for row in data:
            if not isinstance(row, dict):
                continue
            model_id = _normalize_text(row.get("id"), max_length=255)
            if not model_id or model_id in seen:
                continue
            seen.add(model_id)
            items.append(
                {
                    "id": model_id,
                    "label": _normalize_text(row.get("id"), max_length=255) or model_id,
                    "owned_by": _normalize_text(row.get("owned_by"), max_length=255) or "",
                }
            )
    return items


def complete_openai_compatible_text(
    *,
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    api_mode: str = AI_API_MODE_AUTO,
    timeout_seconds: int = 25,
) -> AiTextCompletionResult:
    normalized_base_url = normalize_base_url(base_url)
    normalized_api_key = _normalize_text(api_key, max_length=8000)
    normalized_model = _normalize_text(model, max_length=255)
    normalized_api_mode = normalize_api_mode(api_mode)
    if not normalized_base_url:
        raise AiCenterError("AI Base URL cannot be empty")
    if not normalized_api_key:
        raise AiCenterError("AI API Key cannot be empty")

    models_to_try = [normalized_model] if normalized_model else []
    if not models_to_try:
        models_to_try = [item["id"] for item in list_openai_compatible_models(base_url=normalized_base_url, api_key=normalized_api_key, timeout_seconds=timeout_seconds)]
        if not models_to_try:
            raise AiCenterError("No available AI model was found")

    attempted: set[str] = set()
    last_errors: list[str] = []
    while models_to_try:
        current_model = models_to_try.pop(0)
        if not current_model or current_model in attempted:
            continue
        attempted.add(current_model)
        for attempt in _build_attempt_plan(normalized_api_mode):
            try:
                if attempt.api_mode == AI_API_MODE_RESPONSES:
                    payload = _build_responses_payload(
                        model=current_model,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                    )
                else:
                    payload = _build_chat_completion_payload(
                        model=current_model,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        stream=attempt.stream,
                    )
                endpoint_url = f"{normalized_base_url}{attempt.endpoint_path}"
                if attempt.stream:
                    chunks = _http_request_sse(
                        endpoint_url,
                        api_key=normalized_api_key,
                        payload=payload,
                        timeout=max(30, timeout_seconds),
                    )
                    text = _extract_stream_text(chunks, api_mode=attempt.api_mode)
                else:
                    response = _http_request_json(
                        "POST",
                        endpoint_url,
                        api_key=normalized_api_key,
                        payload=payload,
                        timeout=timeout_seconds,
                    )
                    text = _extract_completion_text(response)
                return AiTextCompletionResult(
                    text=text,
                    used_model=current_model,
                    used_api_mode=attempt.runtime_mode,
                    raw_content=text,
                )
            except AiCenterError as exc:
                last_errors.append(f"{attempt.runtime_mode}: {exc}")

    if not last_errors:
        raise AiCenterError("AI text completion failed")
    if len(last_errors) == 1:
        raise AiCenterError(last_errors[0])
    raise AiCenterError(" ; ".join(last_errors))

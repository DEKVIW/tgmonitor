from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib import error, parse, request

from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.models.config import settings
from app.models.models import SystemSettings, engine, ensure_runtime_storage_tables
from app.schemas.security_models import PublicSecurityConfigResponse, SecurityChallengeVerifyResponse
from app.services.cloudflare_client import CloudflareApiError, CloudflareApiNotFoundError, CloudflareClient
from app.services.secret_codec import decrypt_secret, encrypt_secret
from app.services.system_config_service import (
    SYSTEM_SETTINGS_SINGLETON_ID,
    build_default_system_settings_values,
    ensure_runtime_configuration_seeded,
)


logger = logging.getLogger(__name__)

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
SECURITY_EXTRA_KEY = "cloudflare_security"
SECURITY_JWT_ALGORITHM = "HS256"
SEARCH_CLEARANCE_HEADER = "X-TG-Search-Challenge"
DOMAIN_ACCESS_RULE_DESCRIPTION = "TG Monitor managed domain challenge"
DOMAIN_ACCESS_PHASE = "http_request_firewall_custom"


class SecuritySyncError(RuntimeError):
    def __init__(self, message: str, *, config: dict[str, Any], synced_at: str | None, ruleset_id: str, rule_id: str):
        super().__init__(message)
        self.message = message
        self.config = config
        self.synced_at = synced_at
        self.ruleset_id = ruleset_id
        self.rule_id = rule_id


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value is not None else None


def _from_iso(value: str | None) -> datetime | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
    return bool(value)


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_text(value: Any, default: str = "", *, max_length: int | None = None) -> str:
    normalized = "" if value is None else str(value).strip()
    if not normalized:
        normalized = default
    if max_length is not None:
        normalized = normalized[:max_length]
    return normalized


def _default_storage_values() -> dict[str, Any]:
    return {
        "turnstile_site_key": "",
        "turnstile_secret_encrypted": "",
        "login_challenge_enabled": False,
        "search_challenge_enabled": False,
        "search_challenge_scope": "guest_only",
        "search_challenge_clearance_ttl_seconds": 1800,
        "cloudflare_zone_id": "",
        "cloudflare_api_token_encrypted": "",
        "domain_access_challenge_enabled": False,
        "domain_access_challenge_action": "managed_challenge",
        "domain_access_challenge_expression_mode": "recommended",
        "domain_access_challenge_expression_custom": "",
        "domain_access_rule_id": "",
        "domain_access_ruleset_id": "",
        "domain_access_last_synced_at": "",
        "domain_access_last_sync_status": "never",
        "domain_access_last_sync_message": "",
    }


def _normalize_storage_values(raw_value: Any) -> dict[str, Any]:
    payload = raw_value if isinstance(raw_value, dict) else {}
    normalized = _default_storage_values()

    normalized["turnstile_site_key"] = _coerce_text(payload.get("turnstile_site_key"), "", max_length=512)
    normalized["turnstile_secret_encrypted"] = _coerce_text(
        payload.get("turnstile_secret_encrypted"),
        "",
        max_length=8000,
    )
    normalized["login_challenge_enabled"] = _coerce_bool(payload.get("login_challenge_enabled"), False)
    normalized["search_challenge_enabled"] = _coerce_bool(payload.get("search_challenge_enabled"), False)

    search_scope = _coerce_text(payload.get("search_challenge_scope"), "guest_only", max_length=32)
    normalized["search_challenge_scope"] = search_scope if search_scope in {"guest_only", "all_users"} else "guest_only"
    normalized["search_challenge_clearance_ttl_seconds"] = max(
        300,
        min(86400, _coerce_int(payload.get("search_challenge_clearance_ttl_seconds"), 1800)),
    )

    normalized["cloudflare_zone_id"] = _coerce_text(payload.get("cloudflare_zone_id"), "", max_length=128)
    normalized["cloudflare_api_token_encrypted"] = _coerce_text(
        payload.get("cloudflare_api_token_encrypted"),
        "",
        max_length=8000,
    )

    normalized["domain_access_challenge_enabled"] = _coerce_bool(
        payload.get("domain_access_challenge_enabled"),
        False,
    )
    action = _coerce_text(payload.get("domain_access_challenge_action"), "managed_challenge", max_length=64)
    normalized["domain_access_challenge_action"] = (
        action if action in {"managed_challenge", "js_challenge", "challenge"} else "managed_challenge"
    )
    expression_mode = _coerce_text(
        payload.get("domain_access_challenge_expression_mode"),
        "recommended",
        max_length=32,
    )
    normalized["domain_access_challenge_expression_mode"] = (
        expression_mode if expression_mode in {"recommended", "custom"} else "recommended"
    )
    normalized["domain_access_challenge_expression_custom"] = _coerce_text(
        payload.get("domain_access_challenge_expression_custom"),
        "",
        max_length=4000,
    )
    normalized["domain_access_rule_id"] = _coerce_text(payload.get("domain_access_rule_id"), "", max_length=255)
    normalized["domain_access_ruleset_id"] = _coerce_text(payload.get("domain_access_ruleset_id"), "", max_length=255)
    normalized["domain_access_last_synced_at"] = _coerce_text(
        payload.get("domain_access_last_synced_at"),
        "",
        max_length=255,
    )
    sync_status = _coerce_text(payload.get("domain_access_last_sync_status"), "never", max_length=32)
    normalized["domain_access_last_sync_status"] = (
        sync_status if sync_status in {"never", "success", "error"} else "never"
    )
    normalized["domain_access_last_sync_message"] = _coerce_text(
        payload.get("domain_access_last_sync_message"),
        "",
        max_length=2000,
    )
    return normalized


def _get_recommended_domain_expression() -> str:
    return '(http.request.method in {"GET" "HEAD"} and not starts_with(http.request.uri.path, "/api/") and not starts_with(http.request.uri.path, "/cdn-cgi/") and not (http.request.uri.path contains "."))'


def _build_response_values(storage_values: dict[str, Any]) -> dict[str, Any]:
    turnstile_secret_configured = bool(storage_values["turnstile_secret_encrypted"])
    cloudflare_api_token_configured = bool(storage_values["cloudflare_api_token_encrypted"])
    turnstile_ready = bool(storage_values["turnstile_site_key"] and turnstile_secret_configured)
    return {
        "turnstile_ready": turnstile_ready,
        "turnstile_site_key": storage_values["turnstile_site_key"],
        "turnstile_secret_configured": turnstile_secret_configured,
        "login_challenge_enabled": bool(storage_values["login_challenge_enabled"] and turnstile_ready),
        "search_challenge_enabled": bool(storage_values["search_challenge_enabled"] and turnstile_ready),
        "search_challenge_scope": storage_values["search_challenge_scope"],
        "search_challenge_clearance_ttl_seconds": storage_values["search_challenge_clearance_ttl_seconds"],
        "cloudflare_zone_id": storage_values["cloudflare_zone_id"],
        "cloudflare_api_token_configured": cloudflare_api_token_configured,
        "domain_access_challenge_enabled": bool(storage_values["domain_access_challenge_enabled"]),
        "domain_access_challenge_action": storage_values["domain_access_challenge_action"],
        "domain_access_challenge_expression_mode": storage_values["domain_access_challenge_expression_mode"],
        "domain_access_challenge_expression_custom": storage_values["domain_access_challenge_expression_custom"],
        "domain_access_recommended_expression": _get_recommended_domain_expression(),
        "domain_access_rule_id": storage_values["domain_access_rule_id"],
        "domain_access_ruleset_id": storage_values["domain_access_ruleset_id"],
        "domain_access_last_synced_at": storage_values["domain_access_last_synced_at"] or None,
        "domain_access_last_sync_status": storage_values["domain_access_last_sync_status"],
        "domain_access_last_sync_message": storage_values["domain_access_last_sync_message"],
    }


def _ensure_system_settings_record(session: Session) -> SystemSettings:
    record = session.get(SystemSettings, SYSTEM_SETTINGS_SINGLETON_ID)
    if record is not None:
        return record
    record = SystemSettings(id=SYSTEM_SETTINGS_SINGLETON_ID, **build_default_system_settings_values())
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _read_storage_values(session: Session) -> tuple[SystemSettings, dict[str, Any]]:
    ensure_runtime_configuration_seeded()
    record = _ensure_system_settings_record(session)
    extra_json = record.extra_json if isinstance(record.extra_json, dict) else {}
    return record, _normalize_storage_values(extra_json.get(SECURITY_EXTRA_KEY))


def _write_storage_values(
    session: Session,
    record: SystemSettings,
    storage_values: dict[str, Any],
    *,
    updated_by: str | None,
) -> dict[str, Any]:
    extra_json = dict(record.extra_json) if isinstance(record.extra_json, dict) else {}
    extra_json[SECURITY_EXTRA_KEY] = storage_values
    record.extra_json = extra_json
    record.updated_by = updated_by
    session.add(record)
    session.commit()
    session.refresh(record)
    return _normalize_storage_values((record.extra_json or {}).get(SECURITY_EXTRA_KEY))


def _validate_merged_storage_values(storage_values: dict[str, Any]) -> None:
    turnstile_ready = bool(storage_values["turnstile_site_key"] and storage_values["turnstile_secret_encrypted"])
    if (storage_values["login_challenge_enabled"] or storage_values["search_challenge_enabled"]) and not turnstile_ready:
        raise ValueError("启用登录或搜索质询前，需要先配置 Turnstile Site Key 和 Secret Key")
    if (
        storage_values["domain_access_challenge_enabled"]
        and storage_values["domain_access_challenge_expression_mode"] == "custom"
        and not storage_values["domain_access_challenge_expression_custom"]
    ):
        raise ValueError("启用自定义域名访问表达式时，必须填写 Cloudflare 规则表达式")


def get_security_config_values() -> dict[str, Any]:
    try:
        ensure_runtime_storage_tables()
        with Session(engine) as session:
            _, storage_values = _read_storage_values(session)
            return _build_response_values(storage_values)
    except Exception as exc:
        logger.warning("Failed to load security settings, falling back to defaults: %s", exc)
        return _build_response_values(_default_storage_values())


def get_public_security_config_values() -> dict[str, Any]:
    values = get_security_config_values()
    response = PublicSecurityConfigResponse(**values)
    return response.model_dump()


def apply_security_config(values: dict[str, Any], updated_by: str | None = None) -> dict[str, Any]:
    payload = values if isinstance(values, dict) else {}
    ensure_runtime_storage_tables()
    with Session(engine) as session:
        record, current_storage = _read_storage_values(session)
        merged_storage = dict(current_storage)

        merged_storage["turnstile_site_key"] = _coerce_text(payload.get("turnstile_site_key"), "", max_length=512)
        merged_storage["login_challenge_enabled"] = _coerce_bool(payload.get("login_challenge_enabled"), False)
        merged_storage["search_challenge_enabled"] = _coerce_bool(payload.get("search_challenge_enabled"), False)
        search_scope = _coerce_text(payload.get("search_challenge_scope"), "guest_only", max_length=32)
        merged_storage["search_challenge_scope"] = search_scope if search_scope in {"guest_only", "all_users"} else "guest_only"
        merged_storage["search_challenge_clearance_ttl_seconds"] = max(
            300,
            min(86400, _coerce_int(payload.get("search_challenge_clearance_ttl_seconds"), 1800)),
        )
        merged_storage["cloudflare_zone_id"] = _coerce_text(payload.get("cloudflare_zone_id"), "", max_length=128)
        merged_storage["domain_access_challenge_enabled"] = _coerce_bool(
            payload.get("domain_access_challenge_enabled"),
            False,
        )

        action = _coerce_text(payload.get("domain_access_challenge_action"), "managed_challenge", max_length=64)
        merged_storage["domain_access_challenge_action"] = (
            action if action in {"managed_challenge", "js_challenge", "challenge"} else "managed_challenge"
        )
        expression_mode = _coerce_text(
            payload.get("domain_access_challenge_expression_mode"),
            "recommended",
            max_length=32,
        )
        merged_storage["domain_access_challenge_expression_mode"] = (
            expression_mode if expression_mode in {"recommended", "custom"} else "recommended"
        )
        merged_storage["domain_access_challenge_expression_custom"] = _coerce_text(
            payload.get("domain_access_challenge_expression_custom"),
            "",
            max_length=4000,
        )

        if _coerce_bool(payload.get("clear_turnstile_secret"), False):
            merged_storage["turnstile_secret_encrypted"] = ""
        elif _coerce_text(payload.get("turnstile_secret"), "", max_length=4000):
            merged_storage["turnstile_secret_encrypted"] = encrypt_secret(str(payload.get("turnstile_secret") or ""))

        if _coerce_bool(payload.get("clear_cloudflare_api_token"), False):
            merged_storage["cloudflare_api_token_encrypted"] = ""
        elif _coerce_text(payload.get("cloudflare_api_token"), "", max_length=4000):
            merged_storage["cloudflare_api_token_encrypted"] = encrypt_secret(str(payload.get("cloudflare_api_token") or ""))

        _validate_merged_storage_values(merged_storage)
        stored_values = _write_storage_values(session, record, merged_storage, updated_by=updated_by)
        return _build_response_values(stored_values)


def _decode_turnstile_secret(storage_values: dict[str, Any]) -> str:
    return decrypt_secret(
        storage_values["turnstile_secret_encrypted"],
        error_message="Unable to decrypt Cloudflare Turnstile secret; please verify SECRET_SALT",
    )


def _decode_cloudflare_api_token(storage_values: dict[str, Any]) -> str:
    return decrypt_secret(
        storage_values["cloudflare_api_token_encrypted"],
        error_message="Unable to decrypt Cloudflare API token; please verify SECRET_SALT",
    )


def is_login_challenge_enabled() -> bool:
    values = get_security_config_values()
    return bool(values["login_challenge_enabled"] and values["turnstile_ready"])


def is_search_challenge_required(search_query: str | None, current_user: dict[str, Any] | None) -> bool:
    if not (search_query or "").strip():
        return False
    values = get_security_config_values()
    if not values["search_challenge_enabled"] or not values["turnstile_ready"]:
        return False
    if current_user is None:
        return True
    return values["search_challenge_scope"] == "all_users"


def verify_turnstile_token(
    turnstile_token: str,
    *,
    remote_ip: str | None = None,
    expected_action: str | None = None,
) -> tuple[bool, str]:
    normalized_token = (turnstile_token or "").strip()
    if not normalized_token:
        return False, "缺少 Turnstile 验证令牌"

    ensure_runtime_storage_tables()
    with Session(engine) as session:
        _, storage_values = _read_storage_values(session)

    if not storage_values["turnstile_site_key"] or not storage_values["turnstile_secret_encrypted"]:
        return False, "Turnstile 尚未完成配置"

    secret = _decode_turnstile_secret(storage_values)
    payload = {
        "secret": secret,
        "response": normalized_token,
    }
    if remote_ip:
        payload["remoteip"] = remote_ip

    body = parse.urlencode(payload).encode("utf-8")
    req = request.Request(
        TURNSTILE_VERIFY_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=10) as response:
            raw_body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        return False, f"Cloudflare Turnstile 校验失败: HTTP {exc.code}"
    except error.URLError as exc:
        return False, f"Cloudflare Turnstile 校验失败: {exc.reason}"

    try:
        parsed = json.loads(raw_body)
    except Exception as exc:
        logger.warning("Failed to parse Turnstile verification response: %s; body=%r", exc, raw_body[:500])
        return False, "Cloudflare Turnstile 返回了无效响应"

    success = bool(parsed.get("success"))
    if not success:
        error_codes = parsed.get("error-codes") or []
        if isinstance(error_codes, list) and error_codes:
            return False, "Turnstile 校验未通过: " + ", ".join(str(item) for item in error_codes)
        return False, "Turnstile 校验未通过"

    actual_action = (parsed.get("action") or "").strip()
    if expected_action and actual_action and actual_action != expected_action:
        return False, "Turnstile 动作校验不匹配"

    return True, "ok"


def ensure_login_challenge_passed(turnstile_token: str | None, *, remote_ip: str | None = None) -> None:
    if not is_login_challenge_enabled():
        return
    success, detail = verify_turnstile_token(turnstile_token or "", remote_ip=remote_ip, expected_action="login")
    if not success:
        raise ValueError(detail)


def _build_search_clearance_token(*, current_user: dict[str, Any] | None, ttl_seconds: int) -> SecurityChallengeVerifyResponse:
    audience = f"user:{current_user['username']}" if current_user else "guest"
    expires_at = _utc_now() + timedelta(seconds=ttl_seconds)
    payload = {
        "sub": audience,
        "type": "search_challenge",
        "exp": expires_at,
    }
    clearance_token = jwt.encode(payload, settings.SECRET_SALT, algorithm=SECURITY_JWT_ALGORITHM)
    return SecurityChallengeVerifyResponse(
        clearance_token=clearance_token,
        expires_at=_to_iso(expires_at) or "",
        ttl_seconds=ttl_seconds,
    )


def verify_and_issue_search_clearance(
    turnstile_token: str,
    *,
    current_user: dict[str, Any] | None,
    remote_ip: str | None = None,
) -> SecurityChallengeVerifyResponse:
    values = get_security_config_values()
    if not values["search_challenge_enabled"] or not values["turnstile_ready"]:
        raise ValueError("搜索质询尚未启用")
    success, detail = verify_turnstile_token(turnstile_token, remote_ip=remote_ip, expected_action="search")
    if not success:
        raise ValueError(detail)
    return _build_search_clearance_token(
        current_user=current_user,
        ttl_seconds=int(values["search_challenge_clearance_ttl_seconds"]),
    )


def ensure_search_challenge_clearance(
    search_query: str | None,
    current_user: dict[str, Any] | None,
    *,
    clearance_token: str | None,
) -> None:
    if not is_search_challenge_required(search_query, current_user):
        return

    normalized_token = (clearance_token or "").strip()
    if not normalized_token:
        raise ValueError("搜索前请先完成人机验证")

    try:
        payload = jwt.decode(normalized_token, settings.SECRET_SALT, algorithms=[SECURITY_JWT_ALGORITHM])
    except JWTError as exc:
        raise ValueError("搜索人机验证已失效，请重新验证") from exc

    if payload.get("type") != "search_challenge":
        raise ValueError("搜索人机验证令牌无效")

    expected_subject = f"user:{current_user['username']}" if current_user else "guest"
    if payload.get("sub") != expected_subject:
        raise ValueError("搜索人机验证令牌与当前身份不匹配")


def _build_domain_rule_definition(storage_values: dict[str, Any]) -> dict[str, Any]:
    expression_mode = storage_values["domain_access_challenge_expression_mode"]
    expression = (
        storage_values["domain_access_challenge_expression_custom"]
        if expression_mode == "custom"
        else _get_recommended_domain_expression()
    )
    return {
        "action": storage_values["domain_access_challenge_action"],
        "description": DOMAIN_ACCESS_RULE_DESCRIPTION,
        "enabled": bool(storage_values["domain_access_challenge_enabled"]),
        "expression": expression,
    }


def _find_managed_rule(entrypoint: dict[str, Any], storage_values: dict[str, Any]) -> tuple[str, dict[str, Any]] | tuple[None, None]:
    rules = entrypoint.get("rules")
    if not isinstance(rules, list):
        return None, None

    preferred_rule_id = storage_values["domain_access_rule_id"]
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        if preferred_rule_id and rule.get("id") == preferred_rule_id:
            return rule.get("id"), rule

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        if (rule.get("description") or "").strip() == DOMAIN_ACCESS_RULE_DESCRIPTION:
            return rule.get("id"), rule

    return None, None


def _extract_rule_id_from_response(result: dict[str, Any], storage_values: dict[str, Any]) -> str:
    if isinstance(result.get("id"), str):
        return str(result["id"])
    found_rule_id, _ = _find_managed_rule(result, storage_values)
    return found_rule_id or ""


def sync_domain_access_challenge(updated_by: str | None = None) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    with Session(engine) as session:
        record, storage_values = _read_storage_values(session)
        if not storage_values["cloudflare_zone_id"]:
            raise ValueError("同步域名访问质询前，需要先填写 Cloudflare Zone ID")
        if not storage_values["cloudflare_api_token_encrypted"]:
            raise ValueError("同步域名访问质询前，需要先填写 Cloudflare API Token")

        client = CloudflareClient(_decode_cloudflare_api_token(storage_values))
        try:
            try:
                entrypoint = client.get_phase_entrypoint_ruleset(storage_values["cloudflare_zone_id"], DOMAIN_ACCESS_PHASE)
            except CloudflareApiNotFoundError:
                entrypoint = {}

            ruleset_id = str(entrypoint.get("id") or "")
            existing_rule_id, _ = _find_managed_rule(entrypoint, storage_values)

            if storage_values["domain_access_challenge_enabled"]:
                rule_definition = _build_domain_rule_definition(storage_values)
                if not entrypoint:
                    created_entrypoint = client.create_phase_entrypoint_ruleset(
                        storage_values["cloudflare_zone_id"],
                        DOMAIN_ACCESS_PHASE,
                        rules=[rule_definition],
                    )
                    ruleset_id = str(created_entrypoint.get("id") or "")
                    created_rule_id, _ = _find_managed_rule(created_entrypoint, storage_values)
                    existing_rule_id = created_rule_id
                elif existing_rule_id:
                    updated_rule = client.update_rule(
                        storage_values["cloudflare_zone_id"],
                        ruleset_id,
                        existing_rule_id,
                        rule_definition,
                    )
                    existing_rule_id = _extract_rule_id_from_response(updated_rule, storage_values) or existing_rule_id or ""
                else:
                    created_rule = client.create_rule(
                        storage_values["cloudflare_zone_id"],
                        ruleset_id,
                        _build_domain_rule_definition(storage_values),
                    )
                    existing_rule_id = _extract_rule_id_from_response(created_rule, storage_values)
                    if not existing_rule_id:
                        refreshed_entrypoint = client.get_phase_entrypoint_ruleset(
                            storage_values["cloudflare_zone_id"],
                            DOMAIN_ACCESS_PHASE,
                        )
                        existing_rule_id, _ = _find_managed_rule(refreshed_entrypoint, storage_values)

                sync_message = "Cloudflare 域名访问质询规则已同步"
            else:
                if entrypoint and existing_rule_id:
                    client.delete_rule(storage_values["cloudflare_zone_id"], ruleset_id, existing_rule_id)
                existing_rule_id = ""
                sync_message = "Cloudflare 域名访问质询规则已移除"

            storage_values["domain_access_ruleset_id"] = ruleset_id
            storage_values["domain_access_rule_id"] = existing_rule_id or ""
            storage_values["domain_access_last_synced_at"] = _to_iso(_utc_now()) or ""
            storage_values["domain_access_last_sync_status"] = "success"
            storage_values["domain_access_last_sync_message"] = sync_message
            stored_values = _write_storage_values(session, record, storage_values, updated_by=updated_by)
            return {
                "success": True,
                "status": "success",
                "message": sync_message,
                "synced_at": stored_values["domain_access_last_synced_at"] or None,
                "ruleset_id": stored_values["domain_access_ruleset_id"],
                "rule_id": stored_values["domain_access_rule_id"],
                "config": _build_response_values(stored_values),
            }
        except (CloudflareApiError, ValueError) as exc:
            storage_values["domain_access_last_synced_at"] = _to_iso(_utc_now()) or ""
            storage_values["domain_access_last_sync_status"] = "error"
            storage_values["domain_access_last_sync_message"] = str(exc)
            stored_values = _write_storage_values(session, record, storage_values, updated_by=updated_by)
            raise SecuritySyncError(
                str(exc),
                config=_build_response_values(stored_values),
                synced_at=stored_values["domain_access_last_synced_at"] or None,
                ruleset_id=stored_values["domain_access_ruleset_id"],
                rule_id=stored_values["domain_access_rule_id"],
            ) from exc

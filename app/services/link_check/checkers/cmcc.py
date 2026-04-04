from __future__ import annotations

import asyncio
import base64
import json
import os
import time
from urllib.parse import parse_qs, urlparse

import aiohttp
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from ..result import REASON_EXCEPTION, REASON_HTTP, REASON_NETWORK, REASON_TIMEOUT, LinkTarget
from ..platforms import PLATFORM_139
from .base import BaseChecker

_API_URL = (
    "https://share-kd-njs.yun.139.com/"
    "yun-share/richlifeApp/devapp/IOutLink/getOutLinkInfoV6"
)
_AES_KEY = b"PVGDwmcvfs1uV3d1"
_PASSCODE_KEYS = ("pwd", "code", "passwd", "accessCode")
_REQUIRES_CODE_MARKERS = (
    "\u63d0\u53d6\u7801",
    "\u8bbf\u95ee\u7801",
    "\u5bc6\u7801",
)
_INVALID_MARKERS = (
    "\u4e0d\u5b58\u5728",
    "\u5df2\u5931\u6548",
    "\u5df2\u5220\u9664",
    "\u8fdd\u89c4",
    "\u53d6\u6d88",
)
_RATE_LIMIT_MARKERS = (
    "\u9891\u7e41",
    "\u9650\u5236",
    "\u98ce\u63a7",
    "\u9a8c\u8bc1",
    "captcha",
)


def _contains_marker(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in markers)


def _extract_share_id(url: str) -> str:
    parsed = urlparse(url)
    fragment = (parsed.fragment or "").lstrip("#")
    if "/w/i/" in fragment:
        return fragment.split("/w/i/", 1)[1].split("?", 1)[0].split("/", 1)[0]

    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) >= 3 and path_parts[-3:] == ["shareweb", "w", "i"]:
        return parse_qs(parsed.query).get("id", [""])[0]
    if len(path_parts) >= 3 and path_parts[-2] == "i":
        return path_parts[-1]

    query = parsed.query or ""
    query_values = parse_qs(query)
    for key in ("linkID", "id", "shareId", "sid"):
        value = query_values.get(key, [""])[0]
        if value:
            return value
    if parsed.netloc.lower().endswith("caiyun.139.com") and query and "=" not in query:
        return query.split("&", 1)[0]
    return ""


def _extract_passcode(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in _PASSCODE_KEYS:
        value = query.get(key, [""])[0]
        if value:
            return value

    if parsed.fragment:
        fragment_query = parse_qs(parsed.fragment.split("?", 1)[1] if "?" in parsed.fragment else "")
        for key in _PASSCODE_KEYS:
            value = fragment_query.get(key, [""])[0]
            if value:
                return value
    return ""


def _encrypt_payload(payload: dict) -> str:
    plaintext = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(_AES_KEY), modes.CBC(iv))
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(iv + encrypted).decode("ascii")


def _decrypt_payload(payload: str) -> str:
    raw = base64.b64decode(payload)
    if len(raw) < 32:
        raise ValueError("Encrypted payload is too short")

    iv = raw[:16]
    encrypted = raw[16:]
    cipher = Cipher(algorithms.AES(_AES_KEY), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded = decryptor.update(encrypted) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    plaintext = unpadder.update(padded) + unpadder.finalize()
    return plaintext.decode("utf-8")


class CMCCChecker(BaseChecker):
    checker_name = "mobile139_api"

    def __init__(self, *, timeout: float = 15.0):
        super().__init__(PLATFORM_139, timeout=timeout)
        self.platform = PLATFORM_139
        self.max_concurrent = 2
        self.delay_range = (1.0, 1.8)
        self.max_requests_per_second = 2

    async def check(self, target: LinkTarget, http_session: aiohttp.ClientSession):
        share_id = _extract_share_id(target.resolved_url)
        if not share_id:
            return self.format_error_result(target, error="Unable to extract 139 share id")

        passcode = _extract_passcode(target.resolved_url)
        request_payload = {
            "getOutLinkInfoReq": {
                "account": "",
                "linkID": share_id,
                "passwd": passcode,
                "caSrt": 1,
                "coSrt": 1,
                "srtDr": 0,
                "bNum": 1,
                "pCaID": "root",
                "eNum": 200,
            },
            "commonAccountInfo": {
                "account": "",
                "accountType": 1,
            },
        }

        started_at = time.perf_counter()
        try:
            encrypted_payload = _encrypt_payload(request_payload)
            await self.apply_rate_limit()
            async with http_session.post(
                _API_URL,
                json=encrypted_payload,
                headers={
                    "accept": "application/json, text/plain, */*",
                    "content-type": "application/json",
                    "hcy-cool-flag": "1",
                    "x-deviceinfo": (
                        "||3|12.27.0|chrome|131.0.0.0|"
                        "5c7c68368f048245e1ce47f1c0f8f2d0||windows 10|1536X695|zh-CN|||"
                    ),
                },
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as response:
                response_time = time.perf_counter() - started_at
                body = await response.text(errors="ignore")

                if response.status == 429:
                    return self.rate_limited_result(
                        target,
                        error="HTTP 429",
                        response_time=response_time,
                        status_code=response.status,
                    )
                if response.status != 200:
                    return self.uncertain_result(
                        target,
                        reason=REASON_HTTP,
                        error=f"HTTP {response.status}",
                        response_time=response_time,
                        status_code=response.status,
                    )

                decrypted_text = _decrypt_payload(body)
                payload = json.loads(decrypted_text)
                result_code = str(payload.get("resultCode") or payload.get("result_code") or "")
                desc = str(payload.get("desc") or payload.get("message") or "")
                combined_text = f"{desc}\n{decrypted_text}"
                data = payload.get("data")

                if result_code == "0" and data is not None:
                    return self.valid_result(
                        target,
                        response_time=response_time,
                        status_code=response.status,
                        meta={"share_id": share_id, "result_code": result_code},
                    )

                if _contains_marker(combined_text, _REQUIRES_CODE_MARKERS):
                    if not passcode:
                        return self.requires_code_result(
                            target,
                            error=desc or "139 share requires passcode",
                            response_time=response_time,
                            status_code=response.status,
                        )
                    return self.uncertain_result(
                        target,
                        error=desc or "139 share still requires passcode",
                        response_time=response_time,
                        status_code=response.status,
                    )

                if _contains_marker(combined_text, _RATE_LIMIT_MARKERS):
                    return self.rate_limited_result(
                        target,
                        error=desc or "139 API rate limited",
                        response_time=response_time,
                        status_code=response.status,
                    )

                if _contains_marker(combined_text, _INVALID_MARKERS):
                    return self.invalid_result(
                        target,
                        error=desc or combined_text[:120],
                        response_time=response_time,
                        status_code=response.status,
                    )

                return self.uncertain_result(
                    target,
                    error=desc or "Unexpected 139 API response",
                    response_time=response_time,
                    status_code=response.status,
                    meta={"share_id": share_id, "result_code": result_code or None},
                )
        except asyncio.TimeoutError:
            return self.uncertain_result(
                target,
                reason=REASON_TIMEOUT,
                error="Request timeout",
                response_time=time.perf_counter() - started_at,
            )
        except aiohttp.ClientError as exc:
            return self.uncertain_result(
                target,
                reason=REASON_NETWORK,
                error=str(exc),
                response_time=time.perf_counter() - started_at,
            )
        except (ValueError, json.JSONDecodeError) as exc:
            return self.uncertain_result(
                target,
                reason=REASON_EXCEPTION,
                error=str(exc),
                response_time=time.perf_counter() - started_at,
            )

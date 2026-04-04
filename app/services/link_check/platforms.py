from __future__ import annotations

from urllib.parse import urlparse

from .constants import (
    PLATFORM_115,
    PLATFORM_123,
    PLATFORM_ALIYUN,
    PLATFORM_BAIDU,
    PLATFORM_QUARK,
    PLATFORM_TIANYI,
    PLATFORM_UC,
    PLATFORM_XUNLEI,
    UNKNOWN_PLATFORM,
    get_platform_limits as get_base_platform_limits,
)

PLATFORM_139 = "\u0031\u0033\u0039\u4e91\u76d8"

_PLATFORM_ALIASES = {
    "\u8fc5\u96f7": PLATFORM_XUNLEI,
    "\u79fb\u52a8\u4e91\u76d8": PLATFORM_139,
    "\u548c\u5f69\u4e91": PLATFORM_139,
}

_PLATFORM_LIMITS = {
    PLATFORM_139: {
        "max_concurrent": 2,
        "delay_range": (1.0, 1.8),
    }
}


def canonicalize_platform_name(platform: str) -> str:
    if not platform:
        return UNKNOWN_PLATFORM
    return _PLATFORM_ALIASES.get(platform, platform)


def detect_extended_platform_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if not host:
        return UNKNOWN_PLATFORM

    if "yun.139.com" in host or "caiyun.139.com" in host:
        return PLATFORM_139

    for known_platform, domains in {
        PLATFORM_BAIDU: ("pan.baidu.com",),
        PLATFORM_QUARK: ("pan.quark.cn", "pan.qoark.cn", "quark.cn"),
        PLATFORM_ALIYUN: ("www.alipan.com", "alipan.com", "www.aliyundrive.com", "aliyundrive.com"),
        PLATFORM_115: ("115.com", "115cdn.com", "anxia.com"),
        PLATFORM_TIANYI: ("cloud.189.cn", "h5.cloud.189.cn"),
        PLATFORM_123: ("123pan.com", "123pan.cn", "123684.com", "123685.com", "123912.com", "123592.com", "123865.com"),
        PLATFORM_UC: ("drive.uc.cn", "yun.uc.cn", "uc.cn"),
        PLATFORM_XUNLEI: ("pan.xunlei.com",),
    }.items():
        if any(domain in host for domain in domains):
            return known_platform

    return UNKNOWN_PLATFORM


def get_platform_limits(platform: str):
    canonical = canonicalize_platform_name(platform)
    if canonical in _PLATFORM_LIMITS:
        return _PLATFORM_LIMITS[canonical]
    return get_base_platform_limits(canonical)

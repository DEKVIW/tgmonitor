from __future__ import annotations

import re
from typing import Dict, Tuple

PLATFORM_BAIDU = "百度网盘"
PLATFORM_QUARK = "夸克网盘"
PLATFORM_ALIYUN = "阿里云盘"
PLATFORM_115 = "115网盘"
PLATFORM_TIANYI = "天翼云盘"
PLATFORM_123 = "123云盘"
PLATFORM_UC = "UC网盘"
PLATFORM_XUNLEI = "迅雷网盘"
UNKNOWN_PLATFORM = "未知网盘"

ALL_PLATFORMS = (
    PLATFORM_BAIDU,
    PLATFORM_QUARK,
    PLATFORM_ALIYUN,
    PLATFORM_115,
    PLATFORM_TIANYI,
    PLATFORM_123,
    PLATFORM_UC,
    PLATFORM_XUNLEI,
)

DEFAULT_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

PLATFORM_CONFIGS: Dict[str, Dict[str, object]] = {
    PLATFORM_BAIDU: {
        "domains": ("pan.baidu.com",),
        "max_concurrent": 3,
        "delay_range": (0.8, 1.6),
        "max_requests_per_second": 2,
    },
    PLATFORM_QUARK: {
        "domains": ("pan.quark.cn", "pan.qoark.cn", "quark.cn"),
        "max_concurrent": 4,
        "delay_range": (0.4, 0.8),
        "max_requests_per_second": 3,
    },
    PLATFORM_ALIYUN: {
        "domains": ("www.alipan.com", "alipan.com", "www.aliyundrive.com", "aliyundrive.com"),
        "max_concurrent": 4,
        "delay_range": (0.4, 0.8),
        "max_requests_per_second": 3,
    },
    PLATFORM_115: {
        "domains": ("115.com", "115cdn.com", "anxia.com"),
        "max_concurrent": 2,
        "delay_range": (1.0, 1.8),
        "max_requests_per_second": 2,
    },
    PLATFORM_TIANYI: {
        "domains": ("cloud.189.cn", "h5.cloud.189.cn"),
        "max_concurrent": 3,
        "delay_range": (0.6, 1.2),
        "max_requests_per_second": 2,
    },
    PLATFORM_123: {
        "domains": (
            "123pan.com",
            "123pan.cn",
            "123684.com",
            "123685.com",
            "123912.com",
            "123592.com",
            "123865.com",
        ),
        "max_concurrent": 3,
        "delay_range": (0.5, 1.0),
        "max_requests_per_second": 3,
    },
    PLATFORM_UC: {
        "domains": ("drive.uc.cn", "yun.uc.cn", "uc.cn"),
        "max_concurrent": 3,
        "delay_range": (0.8, 1.4),
        "max_requests_per_second": 2,
    },
    PLATFORM_XUNLEI: {
        "domains": ("pan.xunlei.com",),
        "max_concurrent": 2,
        "delay_range": (1.0, 1.6),
        "max_requests_per_second": 2,
    },
    UNKNOWN_PLATFORM: {
        "domains": tuple(),
        "max_concurrent": 2,
        "delay_range": (0.8, 1.4),
        "max_requests_per_second": 1,
    },
}

GENERAL_INVALID_PATTERNS = (
    re.compile(r"页面不存在", re.IGNORECASE),
    re.compile(r"访问被拒绝", re.IGNORECASE),
    re.compile(r"无法访问", re.IGNORECASE),
    re.compile(r"404\s*(?:错误|页面|not\s*found)", re.IGNORECASE),
    re.compile(r"not\s*found", re.IGNORECASE),
)

PLATFORM_INVALID_PATTERNS = {
    PLATFORM_BAIDU: (
        re.compile(r"分享的文件已经被取消", re.IGNORECASE),
        re.compile(r"啊哦，你来晚了", re.IGNORECASE),
        re.compile(r"此链接分享内容可能因为.*无法访问", re.IGNORECASE),
        re.compile(r"分享链接已过期", re.IGNORECASE),
    ),
    PLATFORM_QUARK: (
        re.compile(r"资源不存在", re.IGNORECASE),
        re.compile(r"分享链接不存在", re.IGNORECASE),
        re.compile(r"文件已删除", re.IGNORECASE),
        re.compile(r"链接已失效", re.IGNORECASE),
    ),
    PLATFORM_ALIYUN: (
        re.compile(r"分享不存在", re.IGNORECASE),
        re.compile(r"来晚啦", re.IGNORECASE),
        re.compile(r"分享已取消", re.IGNORECASE),
    ),
    PLATFORM_115: (
        re.compile(r"文件不存在", re.IGNORECASE),
        re.compile(r"分享已取消", re.IGNORECASE),
        re.compile(r"链接已过期", re.IGNORECASE),
    ),
    PLATFORM_TIANYI: (
        re.compile(r"分享不存在", re.IGNORECASE),
        re.compile(r"链接已失效", re.IGNORECASE),
        re.compile(r"文件已被删除", re.IGNORECASE),
    ),
    PLATFORM_123: (
        re.compile(r"分享不存在", re.IGNORECASE),
        re.compile(r"链接已失效", re.IGNORECASE),
    ),
    PLATFORM_UC: (
        re.compile(r"链接已失效", re.IGNORECASE),
        re.compile(r"文件已删除", re.IGNORECASE),
        re.compile(r"已过期", re.IGNORECASE),
    ),
    PLATFORM_XUNLEI: (
        re.compile(r"分享不存在", re.IGNORECASE),
        re.compile(r"链接已失效", re.IGNORECASE),
        re.compile(r"文件已删除", re.IGNORECASE),
    ),
}


def get_platform_config(platform: str) -> Dict[str, object]:
    return PLATFORM_CONFIGS.get(platform, PLATFORM_CONFIGS[UNKNOWN_PLATFORM])


def get_platform_limits(platform: str) -> Dict[str, Tuple[float, float] | int]:
    config = get_platform_config(platform)
    return {
        "max_concurrent": int(config.get("max_concurrent", 2)),
        "delay_range": tuple(config.get("delay_range", (0.8, 1.4))),
    }

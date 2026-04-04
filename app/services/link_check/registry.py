from __future__ import annotations

from .constants import (
    PLATFORM_115,
    PLATFORM_123,
    PLATFORM_ALIYUN,
    PLATFORM_BAIDU,
    PLATFORM_QUARK,
    PLATFORM_TIANYI,
    PLATFORM_UC,
    PLATFORM_XUNLEI,
)
from .checkers.aliyun import AliyunChecker
from .checkers.baidu import BaiduChecker
from .checkers.cmcc import CMCCChecker
from .checkers.generic import GenericLinkChecker
from .checkers.pan115 import Pan115Checker
from .checkers.pan123 import Pan123Checker
from .checkers.quark import QuarkChecker
from .checkers.tianyi import TianyiChecker
from .checkers.uc import UCChecker
from .checkers.xunlei import XunleiChecker
from .platforms import PLATFORM_139


class CheckerRegistry:
    def __init__(self, *, timeout: float = 15.0):
        self._timeout = timeout
        self._checkers = {
            PLATFORM_BAIDU: BaiduChecker(timeout=timeout),
            PLATFORM_QUARK: QuarkChecker(timeout=timeout),
            PLATFORM_ALIYUN: AliyunChecker(timeout=timeout),
            PLATFORM_TIANYI: TianyiChecker(timeout=timeout),
            PLATFORM_123: Pan123Checker(timeout=timeout),
            PLATFORM_115: Pan115Checker(timeout=timeout),
            PLATFORM_UC: UCChecker(timeout=timeout),
            PLATFORM_XUNLEI: XunleiChecker(timeout=timeout),
            PLATFORM_139: CMCCChecker(timeout=timeout),
        }
        self._generic_checkers = {}

    def get_checker(self, platform: str):
        checker = self._checkers.get(platform)
        if checker is not None:
            return checker

        checker = self._generic_checkers.get(platform)
        if checker is None:
            checker = GenericLinkChecker(platform, timeout=self._timeout)
            self._generic_checkers[platform] = checker
        return checker

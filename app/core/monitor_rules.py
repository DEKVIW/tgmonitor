"""Config loader for monitor parsing rules."""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict


RULES_FILE = Path(__file__).resolve().parents[2] / "data" / "monitor_channel_rules.json"
_rules_lock = threading.RLock()
_rules_cache: Dict[str, Any] | None = None
_rules_mtime: float | None = None


def _default_rules() -> Dict[str, Any]:
    return {
        "redirect_query_keys": [
            "u",
            "url",
            "target",
            "target_url",
            "targeturl",
            "dest",
            "destination",
            "redirect",
            "redirect_to",
            "redirect_uri",
            "redirecturl",
            "jump",
            "jump_url",
            "jumpurl",
            "link",
            "href",
            "to",
            "to_url",
            "next",
            "continue",
            "continue_url",
            "r",
            "ru",
        ],
        "netdisk_map": [
            {"name": "夸克网盘", "keys": ["quark", "夸克"]},
            {"name": "阿里云盘", "keys": ["aliyundrive", "aliyun", "阿里", "alipan"]},
            {"name": "百度网盘", "keys": ["baidu", "pan.baidu"]},
            {"name": "115网盘", "keys": ["115.com", "115网盘", "115pan", "115", "115cdn.com"]},
            {"name": "天翼云盘", "keys": ["cloud.189", "天翼", "189.cn"]},
            {"name": "123云盘", "keys": ["123pan.com", "www.123pan.com", "123912.com", "www.123912.com", "123"]},
            {"name": "UC网盘", "keys": ["ucdisk", "uc网盘", "ucloud", "drive.uc.cn"]},
            {"name": "迅雷", "keys": ["xunlei", "thunder", "迅雷"]},
        ],
        "profiles": {
            "default": {
                "title_fields": ["名称", "标题"],
                "metadata": {
                    "source": ["来自", "来源"],
                    "channel": ["频道"],
                    "group": ["群组"],
                    "bot": ["投稿"],
                },
                "ignored_line_prefixes": ["链接", "下载地址", "分享", "网址", "描述区域"],
                "valid_labels": [
                    "主链",
                    "备用",
                    "普码",
                    "高清",
                    "HDR",
                    "SDR",
                    "1080P",
                    "4K",
                    "4K HDR",
                    "4K SDR",
                    "4K DV",
                    "4K EDR",
                    "4K 60FPS",
                    "4K 120FPS",
                    "大包",
                    "大包2",
                    "大包3",
                    "大包4",
                    "大包5",
                    "文件夹1",
                    "文件夹2",
                    "文件夹3",
                    "文件夹4",
                    "文件夹5",
                ],
                "regions": [
                    "北京", "天津", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江",
                    "上海", "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南",
                    "湖北", "湖南", "广东", "广西", "海南", "重庆", "四川", "贵州",
                    "云南", "西藏", "陕西", "甘肃", "青海", "宁夏", "新疆",
                ],
                "course_keywords": [
                    "事业单位", "三支一扶", "公务员", "公基", "综应", "职测", "行测", "申论",
                    "面试", "刷题", "冲刺", "真题", "模考", "系统班", "讲义", "题海",
                    "时政", "方法", "密押", "预测", "押题", "晨读",
                ],
                "categories": ["A类", "B类", "C类", "D类", "E类", "F类"],
                "filter_patterns": [
                    ".*群主自用机场.*守候网络.*9折活动.*",
                    ".*云盘播放器.*VidHub.*",
                ],
            }
        },
        "channel_profiles": {},
    }


def _deep_merge(base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def load_monitor_rules(force_reload: bool = False) -> Dict[str, Any]:
    global _rules_cache, _rules_mtime

    with _rules_lock:
        file_mtime = RULES_FILE.stat().st_mtime if RULES_FILE.exists() else None
        if not force_reload and _rules_cache is not None and file_mtime == _rules_mtime:
            return deepcopy(_rules_cache)

        rules = _default_rules()
        if RULES_FILE.exists():
            file_rules = json.loads(RULES_FILE.read_text(encoding="utf-8"))
            rules = _deep_merge(rules, file_rules)

        _rules_cache = rules
        _rules_mtime = file_mtime
        return deepcopy(rules)


def resolve_channel_profile(channel_name: str | None, rules: Dict[str, Any] | None = None) -> Dict[str, Any]:
    loaded_rules = rules or load_monitor_rules()
    default_profile = deepcopy(loaded_rules["profiles"]["default"])
    if not channel_name:
        return default_profile

    channel_profiles = loaded_rules.get("channel_profiles", {})
    profile_name = channel_profiles.get(channel_name) or channel_profiles.get(channel_name.lower())
    if not profile_name:
        return default_profile

    profile_overrides = loaded_rules.get("profiles", {}).get(profile_name, {})
    return _deep_merge(default_profile, profile_overrides)

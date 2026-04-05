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
        "redirect_resolver": {
            "max_depth": 4,
            "max_redirect_hops": 8,
            "force_get_domains": [
                "t.cn",
                "weibo.cn",
                "weibo.com",
                "t.co",
                "x.com",
                "url.cn",
                "bit.ly",
                "telegra.ph",
            ],
        },
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
                "intermediate_netdisk_domains": {},
            },
            "course_list_default": {
                "content_mode": "course_list",
                "line_message_mode": "per_link_line",
                "netdisk_hint_aliases": {
                    "夸克网盘": ["KK", "QK", "quark", "夸克"],
                    "百度网盘": ["BD", "baidu", "百度", "百度盘"],
                },
                "intermediate_netdisk_domains": {},
            },
            "movie_default": {
                "content_mode": "movie",
                "title_fields": ["名称", "标题", "片名", "剧名"],
                "metadata": {
                    "source": ["来自", "来源"],
                    "channel": ["频道"],
                    "group": ["群组"],
                    "bot": ["投稿"],
                },
                "ignored_line_prefixes": [
                    "链接",
                    "下载地址",
                    "分享",
                    "网址",
                    "搜索",
                    "机场",
                    "公费服",
                ],
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
                    "原盘",
                    "REMUX",
                    "杜比视界",
                    "杜比全景声",
                ],
                "regions": [],
                "course_keywords": [],
                "categories": [
                    "电影",
                    "剧集",
                    "电视剧",
                    "短剧",
                    "综艺",
                    "动漫",
                    "动画",
                    "国漫",
                    "国产",
                    "国产剧",
                    "纪录片",
                ],
                "filter_patterns": [
                    ".*群主自用机场.*",
                    ".*每日同步更新.*",
                    ".*最新热门抖音快手百度番茄红果等付费短剧推荐.*",
                    ".*云盘合作播放器.*",
                    ".*播放器.*字幕问题.*",
                ],
                "movie_description_fields": ["描述", "简介", "剧情", "介绍"],
                "movie_tag_fields": ["标签"],
                "movie_size_fields": ["大小"],
                "movie_noise_fields": ["来自", "频道", "群组", "投稿", "搜索", "机场", "公费服"],
                "movie_meta_fields": ["评分", "TMDB评分", "豆瓣评分", "类型", "地区", "语言", "画质", "质量", "片长", "主演", "导演", "更新", "简介"],
                "intermediate_netdisk_domains": {},
            }
        },
        "channel_profiles": {
            "wpzyk": "course_list_default",
            "vip115hot": "movie_default",
            "xx123pan": "movie_default",
            "gotopan": "movie_default",
            "+h10ulzfxiQZiYTdi": "movie_default",
            "QukanMovie": "movie_default",
            "alyp_1": "movie_default",
            "QuarkFree": "movie_default",
            "tyypzhpd": "movie_default",
            "Lsp115": "movie_default",
            "bdwpzhpd": "movie_default",
            "shareAliyun": "movie_default",
            "Aliyun_4K_Movies": "movie_default",
            "tianyirigeng": "movie_default",
            "+eQXY7Ewx-4I4NDFl": "movie_default",
        },
        "channel_profile_ids": {
            "1817746196": "course_list_default",
        },
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

        netdisk_map = rules.setdefault("netdisk_map", [])
        if not any(
            isinstance(item, dict)
            and any(key in {"yun.139.com", "caiyun.139.com"} for key in item.get("keys", []))
            for item in netdisk_map
        ):
            netdisk_map.append(
                {
                    "name": "\u0031\u0033\u0039\u4e91\u76d8",
                    "keys": [
                        "yun.139.com",
                        "caiyun.139.com",
                    ],
                }
            )

        _rules_cache = rules
        _rules_mtime = file_mtime
        return deepcopy(rules)


def resolve_channel_profile(
    channel_name: str | None,
    rules: Dict[str, Any] | None = None,
    channel_id: int | None = None,
) -> Dict[str, Any]:
    loaded_rules = rules or load_monitor_rules()
    default_profile = deepcopy(loaded_rules["profiles"]["default"])
    channel_profile_ids = loaded_rules.get("channel_profile_ids", {})
    if channel_id is not None:
        profile_name = channel_profile_ids.get(str(channel_id)) or channel_profile_ids.get(channel_id)
        if profile_name:
            profile_overrides = loaded_rules.get("profiles", {}).get(profile_name, {})
            return _deep_merge(default_profile, profile_overrides)

    if not channel_name:
        return default_profile

    channel_profiles = loaded_rules.get("channel_profiles", {})
    profile_name = channel_profiles.get(channel_name) or channel_profiles.get(channel_name.lower())
    if not profile_name:
        return default_profile

    profile_overrides = loaded_rules.get("profiles", {}).get(profile_name, {})
    return _deep_merge(default_profile, profile_overrides)

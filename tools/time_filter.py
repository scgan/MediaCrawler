# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler
# GitHub: https://github.com/NanmiCoder
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#

# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。

"""
按发布时间区间过滤爬取结果的通用模块。

设计目标
--------
1. 统一各平台"时间字段"的口径差异（秒 / 毫秒 / RFC2822 / 日期字符串）。
2. 在 store 层做统一兜底过滤，任何平台、任何抓取模式（search / detail / creator）都生效。
3. 暴露 `is_in_time_range()` 给 core 层调用，用于"只统计通过过滤的条数"，
   避免被过滤掉的数据白白占用 CRAWLER_MAX_NOTES_COUNT 配额。

用法
----
配置文件 config/base_config.py 中：

    ENABLE_TIME_RANGE_FILTER = True      # 总开关
    START_TIME = "2025-03-01"           # 起始（含），留空表示不限制下限
    END_TIME   = "2025-03-15"           # 结束（含），留空表示不限制上限

命令行：

    python main.py --platform xhs --type search --start_time 2025-03-01 --end_time 2025-03-15

注意
----
- 只给日期时：起始按当天 00:00:00，结束按当天 23:59:59 处理（闭区间）。
- 时间粒度只精确到秒，不处理时区以外的复杂语义。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Optional, Tuple

import config

# 注意：这里刻意不 import tools.utils —— 它会经 crawler_util 拉起 playwright，
# 使本模块变得"重"，在纯解析场景下无法独立使用。
# 只用无第三方依赖的 time_util，并自建 logger。
from .time_util import get_time_str_from_unix_time, rfc2822_to_timestamp

logger = logging.getLogger("MediaCrawler")

# 时间戳量级阈值，用于识别毫秒 / 微秒
_SECOND_UPPER_BOUND = 10 ** 11       # 秒级时间戳上限（约公元 5138 年）
_MICROSECOND_LOWER_BOUND = 10 ** 14  # 微秒级时间戳下限

# 纯数字字符串
_DIGITS_RE = re.compile(r"^\d{9,19}$")

# 常见日期时间字符串格式（按优先级尝试）
_DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d",
    "%Y年%m月%d日 %H:%M:%S",
    "%Y年%m月%d日 %H:%M",
    "%Y年%m月%d日",
)

# RFC2822，例如微博的 "Sat Dec 23 17:12:54 +0800 2023"
_RFC2822_RE = re.compile(r"^[A-Za-z]{3}\s+[A-Za-z]{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+[+-]\d{4}\s+\d{4}$")


def parse_user_time(value: Any, is_end: bool = False) -> Optional[int]:
    """
    解析用户传入的时间，返回秒级时间戳；无法解析或为空返回 None。

    :param value: 用户输入，支持 "YYYY-MM-DD"、"YYYY-MM-DD HH:MM:SS"、"YYYY/MM/DD"、时间戳
    :param is_end: True 表示这是区间结束时间，纯日期时补齐到当天 23:59:59
    """
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return _normalize_timestamp(value)

    text = str(value).strip()
    if not text:
        return None

    # 纯数字（时间戳）
    if _DIGITS_RE.match(text):
        return _normalize_timestamp(int(text))

    # 带时分秒
    for fmt in _DATETIME_FORMATS:
        try:
            dt = datetime.strptime(text, fmt)
        except ValueError:
            continue
        # 只给了日期的情况，按 is_end 补齐到当天首尾
        if fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日"):
            dt = dt + timedelta(days=1) - timedelta(seconds=1) if is_end else dt
        return int(dt.timestamp())

    logger.warning(f"[tools.time_filter.parse_user_time] 无法解析时间: {value!r}，将忽略该边界")
    return None


def _normalize_timestamp(value: Any) -> Optional[int]:
    """
    把数字型时间戳归一化到秒。自动识别秒 / 毫秒 / 微秒。
    """
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None

    if number <= 0:
        return None

    if number >= _MICROSECOND_LOWER_BOUND:
        return number // 1_000_000
    if number >= _SECOND_UPPER_BOUND:
        return number // 1000
    return number


def normalize_to_timestamp(value: Any) -> Optional[int]:
    """
    把任意平台的时间值归一化成秒级时间戳。

    支持：
    - 数字 / 数字字符串（自动识别秒 / 毫秒 / 微秒）
    - RFC2822 字符串（微博）
    - "YYYY-MM-DD HH:MM:SS" 等常见日期字符串（贴吧）
    - datetime 对象

    无法解析返回 None（调用方应按"无法判断"处理，默认放行）。
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        return int(value.timestamp())

    if isinstance(value, bool):  # bool 是 int 的子类，单独排除
        return None

    if isinstance(value, (int, float)):
        return _normalize_timestamp(value)

    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None

    if _DIGITS_RE.match(text):
        return _normalize_timestamp(int(text))

    if _RFC2822_RE.match(text):
        try:
            return rfc2822_to_timestamp(text)
        except Exception:  # pragma: no cover - 异常格式交给后续通用解析
            pass

    for fmt in _DATETIME_FORMATS:
        try:
            return int(datetime.strptime(text, fmt).timestamp())
        except ValueError:
            continue

    return None


class TimeRangeFilter:
    """
    闭区间时间过滤器 [start_ts, end_ts]。
    任一边界为 None 表示该侧不限制。
    """

    def __init__(self, start_ts: Optional[int], end_ts: Optional[int]) -> None:
        self.start_ts = start_ts
        self.end_ts = end_ts

        if start_ts is not None and end_ts is not None and start_ts > end_ts:
            logger.warning(
                f"[tools.time_filter] 起始时间({start_ts})晚于结束时间({end_ts})，已自动交换"
            )
            self.start_ts, self.end_ts = end_ts, start_ts

    @property
    def enabled(self) -> bool:
        return self.start_ts is not None or self.end_ts is not None

    def match(self, value: Any) -> bool:
        """
        判断时间值是否落在区间内。
        无法解析出时间时返回 True（放行，避免误杀）。
        """
        if not self.enabled:
            return True

        ts = normalize_to_timestamp(value)
        if ts is None:
            return True

        if self.start_ts is not None and ts < self.start_ts:
            return False
        if self.end_ts is not None and ts > self.end_ts:
            return False
        return True

    def describe(self) -> str:
        def _fmt(ts: Optional[int]) -> str:
            if ts is None:
                return "不限制"
            return get_time_str_from_unix_time(ts)

        return f"{_fmt(self.start_ts)} ~ {_fmt(self.end_ts)}"


# ---------------------------------------------------------------------------
# 各平台时间字段映射
# ---------------------------------------------------------------------------
# 结构: platform -> (内容时间字段, 评论时间字段)
# 字段值可能是 dict 的 key，也可能是对象的属性名（zhihu / tieba 用的是 pydantic model）
PLATFORM_TIME_FIELDS = {
    "xhs": ("time", "create_time"),
    "dy": ("create_time", "create_time"),
    "ks": ("photo.timestamp", "timestamp"),
    "bili": ("View.pubdate", "ctime"),
    "wb": ("mblog.created_at", "created_at"),
    "tieba": ("publish_time", "publish_time"),
    "zhihu": ("created_time", "publish_time"),
}


def _extract_field(item: Any, field: str) -> Any:
    """
    取字段值，同时支持：
    - dict 与对象两种数据形态
    - "photo.timestamp" 形式的嵌套路径（快手把发布时间放在 photo 子结构里）
    """
    if item is None:
        return None

    current = item
    for part in field.split("."):
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(part)
        else:
            current = getattr(current, part, None)
    return current


def get_platform_time_fields(platform: str) -> Tuple[str, str]:
    """返回 (内容时间字段, 评论时间字段)，未知平台回退到常见默认值。"""
    return PLATFORM_TIME_FIELDS.get(platform, ("create_time", "create_time"))


# ---------------------------------------------------------------------------
# 全局过滤器（惰性构建，支持运行时改 config 后重建）
# ---------------------------------------------------------------------------
_filter_cache: Optional[TimeRangeFilter] = None
_filter_cache_key: Optional[Tuple[bool, str, str]] = None


def get_time_range_filter(force_rebuild: bool = False) -> TimeRangeFilter:
    """
    按当前 config 构建（或复用）全局过滤器。
    注意 config 会在 cmd_arg 解析后被覆盖，因此这里按配置值做缓存键。
    """
    global _filter_cache, _filter_cache_key

    enabled = bool(getattr(config, "ENABLE_TIME_RANGE_FILTER", False))
    start_raw = getattr(config, "START_TIME", "") or ""
    end_raw = getattr(config, "END_TIME", "") or ""
    cache_key = (enabled, str(start_raw), str(end_raw))

    if not force_rebuild and _filter_cache is not None and _filter_cache_key == cache_key:
        return _filter_cache

    if not enabled:
        new_filter = TimeRangeFilter(None, None)
    else:
        new_filter = TimeRangeFilter(
            parse_user_time(start_raw, is_end=False),
            parse_user_time(end_raw, is_end=True),
        )
        # 退化窗口保护：start == end 会形成零宽度区间（左闭右闭、宽度 1 秒），
        # 实际会把几乎所有数据过滤掉。调用方（如 zhengwu_analysis）在创建任务时
        # 常把 start_time/end_time 都写成同一个 now 表示「不限制」，这里必须识别并放行。
        # 注意：纯日期（"2026-09-22"）会被补齐成 [00:00:00, 23:59:59]，不会相等，不受影响。
        if (
            new_filter.start_ts is not None
            and new_filter.end_ts is not None
            and new_filter.start_ts >= new_filter.end_ts
        ):
            logger.warning(
                f"[tools.time_filter] 检测到退化时间窗口: {start_raw!r} ~ {end_raw!r}"
                f"（解析为 {new_filter.describe()}），宽度为零，已视为「不限制」。"
                f"若确实需要过滤，请让结束时间晚于起始时间。"
            )
            new_filter = TimeRangeFilter(None, None)
        elif new_filter.enabled:
            logger.info(f"[tools.time_filter] 已启用时间范围过滤: {new_filter.describe()}")

    _filter_cache = new_filter
    _filter_cache_key = cache_key
    return new_filter


def is_in_time_range(value: Any, platform: str = "", kind: str = "content") -> bool:
    """
    最常用入口：判断某个时间值是否通过过滤。

    :param value: 时间值（秒/毫秒/RFC2822/日期字符串均可）
    :param platform: 平台标识，仅用于日志
    :param kind: "content" 或 "comment"，仅用于日志
    """
    return get_time_range_filter().match(value)


def match_item(item: Any, platform: str, kind: str = "content") -> bool:
    """
    直接对一条数据（dict 或对象）做时间过滤，自动按平台取对应字段。

    :param item: 内容或评论数据
    :param platform: xhs / dy / ks / bili / wb / tieba / zhihu
    :param kind: "content" 或 "comment"
    :return: True 表示应当保留
    """
    time_filter = get_time_range_filter()
    if not time_filter.enabled:
        return True

    # 评论默认不参与过滤（跟随所属内容），可通过配置开启
    if kind == "comment" and not getattr(config, "ENABLE_TIME_FILTER_FOR_COMMENTS", False):
        return True

    content_field, comment_field = get_platform_time_fields(platform)
    field = comment_field if kind == "comment" else content_field
    value = _extract_field(item, field)

    passed = time_filter.match(value)
    if not passed:
        logger.info(
            f"[tools.time_filter] 已过滤 {platform} {kind}，字段 {field}={value!r} "
            f"不在范围 {time_filter.describe()} 内"
        )
    return passed


def filter_item_list(items: list, platform: str, kind: str = "content") -> list:
    """批量过滤，返回通过的数据列表。"""
    if not items:
        return items
    return [item for item in items if match_item(item, platform, kind)]


# ---------------------------------------------------------------------------
# 被丢弃内容登记表（防止「内容被过滤、评论却留下」的孤儿评论）
# ---------------------------------------------------------------------------
# 场景：detail / creator 模式下，core 先把要抓评论的 ID 收集好，再调用 store 保存内容。
# 若内容因时间过滤被丢弃，其评论仍会被抓取并落库，产生没有父内容的孤儿评论。
#
# 这里让 store 层在丢弃内容时登记其 ID，评论落库前反查：
# 父内容已被丢弃 -> 评论一并丢弃。
# 采用「只登记被丢弃的、未知 ID 一律放行」的保守策略，避免因调用顺序差异误删评论。

_dropped_content_ids: set = set()
_dropped_registry_active: bool = False


def reset_dropped_content_ids() -> None:
    """清空登记表（主要用于测试，或同一进程内切换任务时）。"""
    global _dropped_registry_active
    _dropped_content_ids.clear()
    _dropped_registry_active = False


def mark_content_dropped(content_id: Any) -> None:
    """登记一个因时间过滤被丢弃的内容 ID。"""
    global _dropped_registry_active
    if content_id is None or content_id == "":
        return
    _dropped_registry_active = True
    _dropped_content_ids.add(str(content_id))


def is_content_dropped(content_id: Any) -> bool:
    """
    判断某内容是否已被时间过滤丢弃。
    未开启过滤 / ID 未知时返回 False（放行），保证不会比修复前更严格。
    """
    if not _dropped_registry_active:
        return False
    if content_id is None or content_id == "":
        return False
    return str(content_id) in _dropped_content_ids


def dropped_content_count() -> int:
    return len(_dropped_content_ids)


# ---------------------------------------------------------------------------
# search 模式专用：守卫器
# ---------------------------------------------------------------------------
# 解决两个问题：
# 1. 被过滤掉的数据不应占用 CRAWLER_MAX_NOTES_COUNT 配额
# 2. 结果按时间倒序时，一旦越过下界就可以停止翻页，省掉大量无效请求
KEEP = "keep"    # 保留，并计入配额
SKIP = "skip"    # 丢弃，不计入配额，继续翻页
STOP = "stop"    # 丢弃，并终止当前关键词翻页


class SearchTimeGuard:
    """
    search 模式下的时间守卫。

    典型用法（以平台 core.py 的 search 循环为例）:

        guard = SearchTimeGuard("xhs", config.CRAWLER_MAX_NOTES_COUNT)
        while page * per_page <= guard.page_budget(per_page):
            ...
            for note_detail in note_details:
                decision = guard.evaluate(note_detail)
                if decision == STOP:
                    stop_paging = True
                    break
                if decision == SKIP:
                    continue
                await store.update(note_detail)   # 只保存通过的
            if stop_paging or guard.reached_limit:
                break
    """

    def __init__(self, platform: str, max_notes_count: int) -> None:
        self.platform = platform
        self.max_notes_count = max_notes_count
        self.kept = 0
        self.dropped = 0
        self.action = str(
            getattr(config, "TIME_FILTER_OUT_OF_RANGE_ACTION", "skip") or "skip"
        ).strip().lower()
        self.enabled = get_time_range_filter().enabled

    @property
    def reached_limit(self) -> bool:
        return self.max_notes_count > 0 and self.kept >= self.max_notes_count

    def page_budget(self, per_page: int) -> int:
        """
        翻页条数预算。
        开启过滤且策略为 skip 时放宽，让"被丢弃"的条目有机会被后续页面补上。
        """
        if not self.enabled or self.action != SKIP:
            return self.max_notes_count
        factor = getattr(config, "TIME_FILTER_PAGE_BUDGET_FACTOR", 10) or 10
        return self.max_notes_count * max(1, int(factor))

    def evaluate(self, item: Any) -> str:
        """
        判定一条内容数据该如何处理，返回 KEEP / SKIP / STOP。
        未开启过滤时恒为 KEEP，行为与原版完全一致。
        """
        if not self.enabled:
            self.kept += 1
            return KEEP

        if match_item(item, self.platform, "content"):
            self.kept += 1
            return KEEP

        self.dropped += 1
        if self.action == STOP:
            return STOP
        if self.action == "keep":  # 配置里 keep 表示仍然保存
            self.kept += 1
            return KEEP
        return SKIP

    def summary(self, keyword: str = "") -> str:
        extra = f" 关键词[{keyword}]" if keyword else ""
        return (
            f"[时间过滤] 统计{extra}: 保留 {self.kept} 条, 丢弃 {self.dropped} 条, "
            f"目标 {self.max_notes_count} 条"
        )

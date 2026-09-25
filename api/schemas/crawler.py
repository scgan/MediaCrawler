# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/api/schemas/crawler.py
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

from enum import Enum
from typing import Optional, Literal, List
from pydantic import BaseModel


class PlatformEnum(str, Enum):
    """Supported media platforms"""
    XHS = "xhs"
    DOUYIN = "dy"
    KUAISHOU = "ks"
    BILIBILI = "bili"
    WEIBO = "wb"
    TIEBA = "tieba"
    ZHIHU = "zhihu"


class LoginTypeEnum(str, Enum):
    """Login method"""
    QRCODE = "qrcode"
    PHONE = "phone"
    COOKIE = "cookie"


class CrawlerTypeEnum(str, Enum):
    """Crawler type"""
    SEARCH = "search"
    DETAIL = "detail"
    CREATOR = "creator"


class SaveDataOptionEnum(str, Enum):
    """Data save option"""
    CSV = "csv"
    DB = "db"
    JSON = "json"
    JSONL = "jsonl"
    SQLITE = "sqlite"
    MONGODB = "mongodb"
    EXCEL = "excel"


class CrawlerStartRequest(BaseModel):
    """Crawler start request"""
    platform: PlatformEnum
    login_type: LoginTypeEnum = LoginTypeEnum.QRCODE
    crawler_type: CrawlerTypeEnum = CrawlerTypeEnum.SEARCH
    keywords: str = ""  # Keywords for search mode
    specified_ids: str = ""  # Post/video ID list for detail mode, comma-separated
    creator_ids: str = ""  # Creator ID list for creator mode, comma-separated
    start_page: int = 1
    max_notes_count: Optional[int] = None  # Max notes/articles to crawl (None = config default)
    enable_comments: bool = True
    enable_sub_comments: bool = False
    save_option: SaveDataOptionEnum = SaveDataOptionEnum.JSONL
    cookies: str = ""
    headless: bool = False

    # ---- 按发布时间区间过滤（与 main.py 的 --start_time / --end_time 对应）----
    # 支持 "YYYY-MM-DD" 或 "YYYY-MM-DD HH:MM:SS"，留空表示该侧不限制。
    # 只给日期时：起始补到当天 00:00:00，结束补到当天 23:59:59（闭区间）。
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    # 区间外数据的处理策略：skip=丢弃并继续翻页补足 | stop=丢弃并终止翻页 | keep=仍然保存
    time_filter_action: Optional[str] = None


class CrawlerStatusResponse(BaseModel):
    """Crawler status response"""
    status: Literal["idle", "running", "stopping", "error"]
    platform: Optional[str] = None
    crawler_type: Optional[str] = None
    started_at: Optional[str] = None
    error_message: Optional[str] = None


class LogEntry(BaseModel):
    """Log entry"""
    id: int
    timestamp: str
    level: Literal["info", "warning", "error", "success", "debug"]
    message: str


class DataFileInfo(BaseModel):
    """Data file information"""
    name: str
    path: str
    size: int
    modified_at: str
    record_count: Optional[int] = None


# ==================== 多平台并行 ====================

class CrawlerBatchStartRequest(BaseModel):
    """批量启动请求：不同平台并行，同一平台受并发上限约束"""
    tasks: List[CrawlerStartRequest]
    # true 时，若某平台槽位已满则等待其空出；false 时直接跳过该平台
    wait_when_busy: bool = False
    # 等待槽位的超时秒数（仅 wait_when_busy=true 时有效）
    wait_timeout: int = 60


class SkippedTask(BaseModel):
    """被跳过的任务"""
    platform: str
    reason: str


class CrawlerBatchStartResponse(BaseModel):
    """批量启动响应"""
    started: List[str]
    skipped: List[SkippedTask]
    started_count: int
    skipped_count: int


class CrawlerTaskInfo(BaseModel):
    """单个任务状态"""
    job_id: str
    platform: str
    status: str
    crawler_type: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    exit_code: Optional[int] = None
    error_message: Optional[str] = None


class CrawlerPoolStatusResponse(BaseModel):
    """任务池状态"""
    max_parallel_platforms: int
    default_platform_max_parallel: int
    running_total: int
    platforms: dict
    jobs: List[CrawlerTaskInfo]

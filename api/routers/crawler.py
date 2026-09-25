
# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/api/routers/crawler.py
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

from fastapi import APIRouter, HTTPException

import json
import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel

from ..schemas import (
    CrawlerBatchStartRequest,
    CrawlerBatchStartResponse,
    CrawlerPoolStatusResponse,
    CrawlerStartRequest,
    CrawlerStatusResponse,
    CrawlerTaskInfo,
    SkippedTask,
)
from ..services import crawler_manager

router = APIRouter(prefix="/crawler", tags=["crawler"])

class RunAndReadRequest(CrawlerStartRequest):
    timeout: int = 300
    limit: int = 100

DATA_DIR = Path(__file__).parent.parent.parent / "data"


def read_jsonl_file(file_path: Path, limit: int = 100) -> dict:
    rows = []
    total = 0

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            total += 1

            if len(rows) < limit:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    rows.append({"raw": line})

    return {
        "file": str(file_path.relative_to(DATA_DIR)),
        "data": rows,
        "total": total
    }


def find_latest_result_file(platform: Optional[str] = None) -> Optional[Path]:
    if not DATA_DIR.exists():
        return None

    candidates = []

    for root, _, filenames in os.walk(DATA_DIR):
        root_path = Path(root)

        for filename in filenames:
            file_path = root_path / filename

            if file_path.suffix.lower() not in {".jsonl", ".json"}:
                continue

            rel_path = str(file_path.relative_to(DATA_DIR)).lower()

            if platform and platform.lower() not in rel_path:
                continue

            candidates.append(file_path)

    if not candidates:
        return None

    return max(candidates, key=lambda p: p.stat().st_mtime)

@router.post("/start")
async def start_crawler(request: CrawlerStartRequest):
    """Start crawler task"""
    success = await crawler_manager.start(request)
    if not success:
        # Handle concurrent/duplicate requests: if process is already running, return 400 instead of 500
        if crawler_manager.process and crawler_manager.process.poll() is None:
            raise HTTPException(status_code=400, detail="Crawler is already running")
        raise HTTPException(status_code=500, detail="Failed to start crawler")

    return {"status": "ok", "message": "Crawler started successfully"}


@router.post("/stop")
async def stop_crawler():
    """Stop crawler task"""
    success = await crawler_manager.stop()
    if not success:
        # Handle concurrent/duplicate requests: if process already exited/doesn't exist, return 400 instead of 500
        if not crawler_manager.process or crawler_manager.process.poll() is not None:
            raise HTTPException(status_code=400, detail="No crawler is running")
        raise HTTPException(status_code=500, detail="Failed to stop crawler")

    return {"status": "ok", "message": "Crawler stopped successfully"}


@router.get("/status", response_model=CrawlerStatusResponse)
async def get_crawler_status():
    """Get crawler status"""
    return crawler_manager.get_status()


@router.get("/logs")
async def get_logs(limit: int = 100):
    """Get recent logs"""
    logs = crawler_manager.logs[-limit:] if limit > 0 else crawler_manager.logs
    return {"logs": [log.model_dump() for log in logs]}


# ============================================================
# 多平台并行：不同平台各自独立进程并行运行
# ============================================================

@router.post("/batch-start", response_model=CrawlerBatchStartResponse)
async def start_crawler_batch(request: CrawlerBatchStartRequest):
    """
    并行启动多个平台任务。

    不同平台互不阻塞；同一平台受并发上限约束（默认 1，
    因为同一平台的 Chromium user_data_dir 是同一目录，并行会锁冲突）。

    被跳过的平台会在 skipped 中返回，调用方可据此重试。
    """
    if not request.tasks:
        raise HTTPException(status_code=400, detail="tasks 不能为空")

    result = await crawler_manager.start_batch(request.tasks)
    return CrawlerBatchStartResponse(
        started=result["started"],
        skipped=[SkippedTask(**item) for item in result["skipped"]],
        started_count=result["started_count"],
        skipped_count=result["skipped_count"],
    )


@router.get("/tasks", response_model=CrawlerPoolStatusResponse)
async def get_pool_status():
    """任务池状态：并发上限、各平台运行数、全部任务明细"""
    status = crawler_manager.get_pool_status()
    return CrawlerPoolStatusResponse(
        max_parallel_platforms=status["max_parallel_platforms"],
        default_platform_max_parallel=status["default_platform_max_parallel"],
        running_total=status["running_total"],
        platforms=status["platforms"],
        jobs=[CrawlerTaskInfo(**job) for job in status["jobs"]],
    )


@router.get("/tasks/{platform}")
async def get_platform_status(platform: str):
    """查询单个平台的任务状态"""
    return crawler_manager.platform_status(platform)


@router.post("/stop/{platform}")
async def stop_platform(platform: str):
    """停止指定平台的所有任务"""
    success = await crawler_manager.stop_platform(platform)
    if not success:
        raise HTTPException(status_code=400, detail=f"平台 {platform} 没有运行中的任务")
    return {"status": "ok", "message": f"平台 {platform} 的任务已停止"}


@router.post("/stop-all")
async def stop_all():
    """停止全部平台的任务"""
    success = await crawler_manager.stop_all()
    if not success:
        raise HTTPException(status_code=400, detail="没有运行中的任务")
    return {"status": "ok", "message": "全部任务已停止"}

# @router.post("/run-and-read")
# async def run_and_read(request: RunAndReadRequest):
#     """
#     Start crawler, wait for completion, then return latest result file as JSON.

#     This endpoint is suitable for small crawling tasks only.
#     For long tasks, use:
#     1. POST /api/crawler/start
#     2. GET /api/crawler/status
#     3. GET /api/data/files
#     4. GET /api/data/files/{file_path}
#     """

#     # 强制使用 jsonl，方便接口读取
#     request.save_option = request.save_option.JSONL

#     success = await crawler_manager.start(request)

#     if not success:
#         if crawler_manager.process and crawler_manager.process.poll() is None:
#             raise HTTPException(status_code=400, detail="Crawler is already running")
#         raise HTTPException(status_code=500, detail="Failed to start crawler")

#     finished = await crawler_manager.wait_until_finished(timeout=request.timeout)

#     if not finished:
#         await crawler_manager.stop()
#         raise HTTPException(status_code=504, detail="Crawler timeout")

#     latest_file = find_latest_result_file(platform=request.platform.value)

#     if not latest_file:
#         return {
#             "status": "ok",
#             "message": "Crawler finished, but no result file found",
#             "data": [],
#             "total": 0
#         }

#     if latest_file.suffix == ".jsonl":
#         result = read_jsonl_file(latest_file, limit=request.limit)
#         return {
#             "status": "ok",
#             "message": "Crawler finished successfully",
#             **result
#         }

#     if latest_file.suffix == ".json":
#         with open(latest_file, "r", encoding="utf-8") as f:
#             data = json.load(f)

#         if isinstance(data, list):
#             return {
#                 "status": "ok",
#                 "message": "Crawler finished successfully",
#                 "file": str(latest_file.relative_to(DATA_DIR)),
#                 "data": data[:request.limit],
#                 "total": len(data)
#             }

#         return {
#             "status": "ok",
#             "message": "Crawler finished successfully",
#             "file": str(latest_file.relative_to(DATA_DIR)),
#             "data": data,
#             "total": 1
#         }

#     raise HTTPException(status_code=400, detail="Unsupported result file type")

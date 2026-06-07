
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

from ..schemas import CrawlerStartRequest, CrawlerStatusResponse
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

@router.post("/run-and-read")
async def run_and_read(request: RunAndReadRequest):
    """
    Start crawler, wait for completion, then return latest result file as JSON.

    This endpoint is suitable for small crawling tasks only.
    For long tasks, use:
    1. POST /api/crawler/start
    2. GET /api/crawler/status
    3. GET /api/data/files
    4. GET /api/data/files/{file_path}
    """

    # 强制使用 jsonl，方便接口读取
    request.save_option = request.save_option.JSONL

    success = await crawler_manager.start(request)

    if not success:
        if crawler_manager.process and crawler_manager.process.poll() is None:
            raise HTTPException(status_code=400, detail="Crawler is already running")
        raise HTTPException(status_code=500, detail="Failed to start crawler")

    finished = await crawler_manager.wait_until_finished(timeout=request.timeout)

    if not finished:
        await crawler_manager.stop()
        raise HTTPException(status_code=504, detail="Crawler timeout")

    latest_file = find_latest_result_file(platform=request.platform.value)

    if not latest_file:
        return {
            "status": "ok",
            "message": "Crawler finished, but no result file found",
            "data": [],
            "total": 0
        }

    if latest_file.suffix == ".jsonl":
        result = read_jsonl_file(latest_file, limit=request.limit)
        return {
            "status": "ok",
            "message": "Crawler finished successfully",
            **result
        }

    if latest_file.suffix == ".json":
        with open(latest_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            return {
                "status": "ok",
                "message": "Crawler finished successfully",
                "file": str(latest_file.relative_to(DATA_DIR)),
                "data": data[:request.limit],
                "total": len(data)
            }

        return {
            "status": "ok",
            "message": "Crawler finished successfully",
            "file": str(latest_file.relative_to(DATA_DIR)),
            "data": data,
            "total": 1
        }

    raise HTTPException(status_code=400, detail="Unsupported result file type")

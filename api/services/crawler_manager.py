# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/api/services/crawler_manager.py
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

import asyncio
import itertools
import subprocess
import signal
import os
import sys
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from datetime import datetime
from pathlib import Path

from ..schemas import CrawlerStartRequest, LogEntry

import config as project_config

from tools.platform_runner import platform_max_parallel

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass
class PlatformJob:
    """单个平台任务（一个独立子进程）"""

    job_id: str
    platform: str
    process: Optional[subprocess.Popen] = None
    status: str = "idle"  # idle | running | stopping | error
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    config: Optional[CrawlerStartRequest] = None
    exit_code: Optional[int] = None
    error_message: Optional[str] = None
    _read_task: Optional[asyncio.Task] = None
    logs: List[LogEntry] = field(default_factory=list)

    @property
    def is_alive(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "platform": self.platform,
            "status": self.status,
            "crawler_type": self.config.crawler_type.value if self.config else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "exit_code": self.exit_code,
            "error_message": self.error_message,
        }


class CrawlerManager:
    """
    多平台任务池。

    不同平台可并行（各自独立子进程，config 天然隔离）；
    同一平台默认串行——因为同一平台的 Chromium user_data_dir 是同一个目录，
    并行打开会触发 profile 锁冲突。并发上限见 config.DEFAULT_PLATFORM_MAX_PARALLEL。

    对外保留原有的单任务接口（start / stop / get_status / logs），
    行为向后兼容；新增批量接口 start_batch / list_tasks / stop_platform / stop_all。
    """

    MAX_LOGS = 500

    def __init__(self):
        self._lock = asyncio.Lock()
        self._jobs: Dict[str, PlatformJob] = {}
        self._job_seq = itertools.count(1)
        self._log_id = 0
        self._logs: List[LogEntry] = []
        # 单一日志队列：WebSocket 广播协程持有该引用，不能被替换
        self._log_queue: Optional[asyncio.Queue] = None
        # 兼容旧代码的单任务视图
        self.status = "idle"
        self.started_at: Optional[datetime] = None
        self.current_config: Optional[CrawlerStartRequest] = None
        self.error_message: Optional[str] = None
        self._project_root = Path(__file__).parent.parent.parent

    # ------------------------------------------------------------------
    # 兼容属性：旧代码与路由会访问 manager.process / logs / status
    # ------------------------------------------------------------------
    @property
    def process(self) -> Optional[subprocess.Popen]:
        """最近一个仍在运行的进程；无运行中任务时返回最后一个进程。

        路由里用 `crawler_manager.process.poll()` 判断是否在跑，
        这里必须返回一个真实 Popen（可能为已退出的），不能返回 None。
        """
        alive = [job.process for job in self._jobs.values() if job.is_alive]
        if alive:
            return alive[-1]
        finished = [job.process for job in self._jobs.values() if job.process]
        return finished[-1] if finished else None

    @property
    def logs(self) -> List[LogEntry]:
        return self._logs

    def get_log_queue(self) -> asyncio.Queue:
        """Get or create log queue（全局唯一，供 WebSocket 广播）"""
        if self._log_queue is None:
            self._log_queue = asyncio.Queue()
        return self._log_queue

    def _create_log_entry(
        self, message: str, level: str = "info", platform: Optional[str] = None
    ) -> LogEntry:
        """Create log entry"""
        self._log_id += 1
        prefix = f"[{platform}] " if platform else ""
        entry = LogEntry(
            id=self._log_id,
            timestamp=datetime.now().strftime("%H:%M:%S"),
            level=level,
            message=f"{prefix}{message}",
        )
        self._logs.append(entry)
        if len(self._logs) > self.MAX_LOGS:
            self._logs = self._logs[-self.MAX_LOGS:]
        return entry

    async def _push_log(self, entry: LogEntry):
        """Push log to queue"""
        if self._log_queue is not None:
            try:
                self._log_queue.put_nowait(entry)
            except asyncio.QueueFull:
                pass

    def _parse_log_level(self, line: str) -> str:
        """Parse log level"""
        line_upper = line.upper()
        if "ERROR" in line_upper or "FAILED" in line_upper:
            return "error"
        elif "WARNING" in line_upper or "WARN" in line_upper:
            return "warning"
        elif "SUCCESS" in line_upper or "完成" in line or "成功" in line:
            return "success"
        elif "DEBUG" in line_upper:
            return "debug"
        return "info"

    # ------------------------------------------------------------------
    # 任务池核心
    # ------------------------------------------------------------------
    def _running_for_platform(self, platform: str) -> List[PlatformJob]:
        return [
            job for job in self._jobs.values()
            if job.platform == platform and job.status in ("running", "stopping")
        ]

    def _next_job_id(self, platform: str) -> str:
        return f"{platform}-{next(self._job_seq)}"

    def _sync_aggregate(self) -> None:
        """刷新兼容用的单任务视图（status / current_config / error_message）"""
        running = [job for job in self._jobs.values() if job.status in ("running", "stopping")]
        if running:
            job = running[-1]
            self.status = job.status
            self.current_config = job.config
            self.started_at = job.started_at
            self.error_message = None
            return

        errored = [job for job in self._jobs.values() if job.status == "error"]
        if errored:
            job = errored[-1]
            self.status = "error"
            self.current_config = job.config
            self.started_at = job.started_at
            self.error_message = job.error_message
            return

        self.status = "idle"
        self.current_config = None
        self.started_at = None
        self.error_message = None

    async def _start_job(self, config: CrawlerStartRequest) -> Optional[PlatformJob]:
        """启动单个平台任务；返回 None 表示该平台槽位已满"""
        platform = config.platform.value

        running = self._running_for_platform(platform)
        limit = platform_max_parallel(platform)
        if len(running) >= limit:
            await self._push_log(self._create_log_entry(
                f"平台 {platform} 已有 {len(running)} 个任务在运行"
                f"（上限 {limit}），本次未启动",
                "warning",
                platform,
            ))
            return None

        # 全局并发上限
        all_running = [
            job for job in self._jobs.values() if job.status in ("running", "stopping")
        ]
        global_limit = max(1, int(getattr(project_config, "MAX_PARALLEL_PLATFORMS", 3)))
        if len(all_running) >= global_limit:
            await self._push_log(self._create_log_entry(
                f"全局并发已达上限 {global_limit}，平台 {platform} 排队中",
                "warning",
                platform,
            ))
            return None

        cmd = self._build_command(config)
        entry = self._create_log_entry(f"Starting crawler: {' '.join(cmd)}", "info", platform)
        await self._push_log(entry)

        job = PlatformJob(job_id=self._next_job_id(platform), platform=platform)
        job.config = config

        try:
            popen_kwargs = {}
            if os.name != "nt":
                popen_kwargs["start_new_session"] = True

            job.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                bufsize=1,
                cwd=str(PROJECT_ROOT),
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
                **popen_kwargs,
            )
            job.status = "running"
            job.started_at = datetime.now()
            self._jobs[job.job_id] = job

            entry = self._create_log_entry(
                f"Crawler started on platform: {config.platform.value}, "
                f"type: {config.crawler_type.value}",
                "success",
                platform,
            )
            await self._push_log(entry)

            job._read_task = asyncio.create_task(self._read_output(job))
            return job
        except Exception as e:
            job.status = "error"
            job.error_message = str(e)
            entry = self._create_log_entry(f"Failed to start crawler: {str(e)}", "error", platform)
            await self._push_log(entry)
            return None

    async def start(self, config: CrawlerStartRequest) -> bool:
        """Start crawler process（单平台）"""
        async with self._lock:
            job = await self._start_job(config)
            self._sync_aggregate()
            return job is not None

    async def start_batch(self, configs: List[CrawlerStartRequest]) -> Dict[str, object]:
        """
        并行启动多个平台任务。

        不同平台互不阻塞；同一平台受 platform_max_parallel 约束，
        超限的任务直接跳过（不排队），调用方据此决定是否重试。
        """
        async with self._lock:
            started: List[str] = []
            skipped: List[Dict[str, str]] = []

            for config in configs:
                platform = config.platform.value
                job = await self._start_job(config)
                if job:
                    started.append(job.job_id)
                else:
                    skipped.append({
                        "platform": platform,
                        "reason": "该平台任务数已达上限或全局并发已满",
                    })

            self._sync_aggregate()
            return {
                "started": started,
                "skipped": skipped,
                "started_count": len(started),
                "skipped_count": len(skipped),
            }

    def list_tasks(self) -> List[dict]:
        """所有任务的状态"""
        return [job.to_dict() for job in self._jobs.values()]

    def get_task(self, job_id: str) -> Optional[dict]:
        job = self._jobs.get(job_id)
        return job.to_dict() if job else None

    def platform_status(self, platform: str) -> dict:
        """某平台的聚合状态"""
        jobs = [job for job in self._jobs.values() if job.platform == platform]
        if not jobs:
            return {"platform": platform, "status": "idle", "running": 0, "total": 0}
        running = [job for job in jobs if job.status in ("running", "stopping")]
        status = "running" if running else (
            "error" if any(job.status == "error" for job in jobs) else "idle"
        )
        return {
            "platform": platform,
            "status": status,
            "running": len(running),
            "total": len(jobs),
            "jobs": [job.to_dict() for job in jobs],
        }

    # ------------------------------------------------------------------
    # 停止
    # ------------------------------------------------------------------
    async def _stop_job(self, job: PlatformJob) -> bool:
        if not job.process or job.process.poll() is not None:
            return False

        job.status = "stopping"
        await self._push_log(self._create_log_entry(
            "Sending SIGTERM to crawler process...", "warning", job.platform
        ))

        try:
            if os.name != "nt":
                os.killpg(os.getpgid(job.process.pid), signal.SIGTERM)
            else:
                job.process.send_signal(signal.SIGTERM)

            for _ in range(30):
                if job.process.poll() is not None:
                    break
                await asyncio.sleep(0.5)

            if job.process.poll() is None:
                await self._push_log(self._create_log_entry(
                    "Process not responding, sending SIGKILL...", "warning", job.platform
                ))
                if os.name != "nt":
                    os.killpg(os.getpgid(job.process.pid), signal.SIGKILL)
                else:
                    job.process.kill()

            await self._push_log(self._create_log_entry(
                "Crawler process terminated", "info", job.platform
            ))
        except Exception as e:
            await self._push_log(self._create_log_entry(
                f"Error stopping crawler: {str(e)}", "error", job.platform
            ))

        job.status = "idle"
        job.finished_at = datetime.now()
        if job._read_task:
            job._read_task.cancel()
            job._read_task = None
        return True

    async def stop(self) -> bool:
        """停止全部运行中的任务"""
        async with self._lock:
            targets = [
                job for job in self._jobs.values()
                if job.status in ("running", "stopping")
            ]
            results = [await self._stop_job(job) for job in targets]
            self._sync_aggregate()
            return any(results)

    async def stop_platform(self, platform: str) -> bool:
        """停止指定平台的所有任务"""
        async with self._lock:
            targets = [
                job for job in self._jobs.values()
                if job.platform == platform and job.status in ("running", "stopping")
            ]
            results = [await self._stop_job(job) for job in targets]
            self._sync_aggregate()
            return any(results)

    async def stop_all(self) -> bool:
        """停止全部任务（含非运行中的也一并清理读取任务）"""
        return await self.stop()

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------
    def get_status(self) -> dict:
        """聚合状态（兼容旧格式）"""
        running = [job for job in self._jobs.values() if job.status in ("running", "stopping")]
        if running:
            job = running[-1]
            return {
                "status": "running",
                "platform": job.platform,
                "crawler_type": job.config.crawler_type.value if job.config else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "error_message": None,
                "running_count": len(running),
            }

        errored = [job for job in self._jobs.values() if job.status == "error"]
        if errored:
            job = errored[-1]
            return {
                "status": "error",
                "platform": job.platform,
                "crawler_type": job.config.crawler_type.value if job.config else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "error_message": job.error_message,
                "running_count": 0,
            }

        return {
            "status": "idle",
            "platform": None,
            "crawler_type": None,
            "started_at": None,
            "error_message": None,
            "running_count": 0,
        }

    def get_pool_status(self) -> dict:
        """任务池整体状态"""
        by_platform: Dict[str, dict] = {}
        for job in self._jobs.values():
            item = by_platform.setdefault(job.platform, {"running": 0, "total": 0, "error": 0})
            item["total"] += 1
            if job.status in ("running", "stopping"):
                item["running"] += 1
            elif job.status == "error":
                item["error"] += 1

        return {
            "max_parallel_platforms": int(
                getattr(project_config, "MAX_PARALLEL_PLATFORMS", 3)
            ),
            "default_platform_max_parallel": int(
                getattr(project_config, "DEFAULT_PLATFORM_MAX_PARALLEL", 1)
            ),
            "running_total": sum(
                1 for job in self._jobs.values() if job.status in ("running", "stopping")
            ),
            "platforms": by_platform,
            "jobs": self.list_tasks(),
        }

    async def wait_until_finished(self, timeout: int = 300) -> bool:
        """
        Wait until all crawler processes finished.

        :param timeout: max wait seconds
        :return: True if all finished, False if timeout
        """
        waited = 0
        while waited < timeout:
            if not any(job.is_alive for job in self._jobs.values()):
                return True
            await asyncio.sleep(1)
            waited += 1
        return False

    # ------------------------------------------------------------------
    # 子进程输出
    # ------------------------------------------------------------------
    def _build_command(self, config: CrawlerStartRequest) -> list:
        """Build main.py command line arguments"""
        cmd = [sys.executable, "main.py"]

        cmd.extend(["--platform", config.platform.value])
        cmd.extend(["--lt", config.login_type.value])
        cmd.extend(["--type", config.crawler_type.value])
        cmd.extend(["--save_data_option", config.save_option.value])

        # Pass different arguments based on crawler type
        if config.crawler_type.value == "search" and config.keywords:
            cmd.extend(["--keywords", config.keywords])
        elif config.crawler_type.value == "detail" and config.specified_ids:
            cmd.extend(["--specified_id", config.specified_ids])
        elif config.crawler_type.value == "creator" and config.creator_ids:
            cmd.extend(["--creator_id", config.creator_ids])

        if config.start_page != 1:
            cmd.extend(["--start", str(config.start_page)])

        if config.max_notes_count and config.max_notes_count > 0:
            cmd.extend(["--max_notes_count", str(config.max_notes_count)])

        cmd.extend(["--get_comment", "true" if config.enable_comments else "false"])
        cmd.extend(["--get_sub_comment", "true" if config.enable_sub_comments else "false"])

        if config.cookies:
            cmd.extend(["--cookies", config.cookies])

        cmd.extend(["--headless", "true" if config.headless else "false"])

        # 按发布时间区间过滤（任一为空即不限制该侧）
        if getattr(config, "start_time", None):
            cmd.extend(["--start_time", config.start_time])
        if getattr(config, "end_time", None):
            cmd.extend(["--end_time", config.end_time])
        if getattr(config, "time_filter_action", None):
            cmd.extend(["--time_filter_action", config.time_filter_action])

        return cmd

    async def _read_output(self, job: PlatformJob):
        """Asynchronously read process output（按任务隔离）"""
        loop = asyncio.get_event_loop()
        platform = job.platform

        try:
            while job.process and job.process.poll() is None:
                line = await loop.run_in_executor(None, job.process.stdout.readline)
                if line:
                    line = line.strip()
                    if line:
                        level = self._parse_log_level(line)
                        entry = self._create_log_entry(line, level, platform)
                        job.logs.append(entry)
                        await self._push_log(entry)

            if job.process and job.process.stdout:
                remaining = await loop.run_in_executor(None, job.process.stdout.read)
                if remaining:
                    for line in remaining.strip().split("\n"):
                        if line.strip():
                            level = self._parse_log_level(line)
                            entry = self._create_log_entry(line.strip(), level, platform)
                            job.logs.append(entry)
                            await self._push_log(entry)

            if job.status == "running":
                exit_code = job.process.returncode if job.process else -1
                job.exit_code = exit_code
                login_failed_code = getattr(project_config, "LOGIN_FAILED_EXIT_CODE", 2)

                if exit_code == login_failed_code:
                    # 登录失败专用退出码。必须标记为 error：
                    # 否则调用方会看到 idle 而误判成功，最终 0 条数据却无报错。
                    job.status = "error"
                    job.error_message = (
                        "登录失败：浏览器未能在超时前完成登录。"
                        "若运行在无头模式（headless=true），二维码无法展示，请改用以下方式之一："
                        "1) 先用有头模式人工扫码登录一次，复用 browser_data 中保存的登录态；"
                        "2) 使用 cookie 登录（传 cookies 且 login_type=cookie）。"
                    )
                    entry = self._create_log_entry(
                        f"[登录失败] 进程以退出码 {exit_code} 结束，未采集到任何数据。"
                        f"当前 headless={'true' if getattr(job.config, 'headless', False) else 'false'}，"
                        f"浏览器{'无法显示二维码' if getattr(job.config, 'headless', False) else '已显示二维码'}。",
                        "error",
                        platform,
                    )
                    await self._push_log(entry)
                elif exit_code == 0:
                    entry = self._create_log_entry(
                        "Crawler completed successfully", "success", platform
                    )
                    await self._push_log(entry)
                    job.status = "idle"
                else:
                    entry = self._create_log_entry(
                        f"Crawler exited with code: {exit_code}", "warning", platform
                    )
                    await self._push_log(entry)
                    job.status = "idle"

                job.finished_at = datetime.now()
                self._sync_aggregate()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            entry = self._create_log_entry(f"Error reading output: {str(e)}", "error", platform)
            await self._push_log(entry)


# Global singleton
crawler_manager = CrawlerManager()

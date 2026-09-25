# -*- coding: utf-8 -*-
"""
多平台并行执行器。

设计要点
--------
MediaCrawler 的 config 是模块级全局单例，PLATFORM / KEYWORDS / COOKIES 等
平台相关变量写在同一处，单进程内无法让两个平台各用一套配置。

因此并行的唯一稳妥方式是**多进程**——每个平台一个独立的 `main.py` 子进程，
各自拥有独立的 config，天然隔离。

隔离性已确认：
  - SAVE_DATA_PATH 按 self.platform 分目录     -> 数据文件不冲突
  - user_data_dir 按 config.PLATFORM 命名      -> 登录态目录不冲突（限不同平台）
  - var.py 全部是 ContextVar                   -> 协程级隔离
  - 各平台 browser_context / ip_proxy_pool     -> 实例属性，各自独立

并发模型：
  - 不同平台：并行（受 MAX_PARALLEL_PLATFORMS 全局上限约束）
  - 同一平台：默认串行（DEFAULT_PLATFORM_MAX_PARALLEL=1）
    因为同一平台的 user_data_dir 是同一个目录，同时打开会触发
    Chromium profile 锁冲突。确需放开须同时满足
    SAVE_LOGIN_STATE=False 且 cookie 登录。
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import config

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class PlatformTaskResult:
    """单个平台的执行结果"""

    platform: str
    success: bool = False
    exit_code: Optional[int] = None
    started_at: float = 0.0
    finished_at: float = 0.0
    error: Optional[str] = None
    timed_out: bool = False
    stdout_tail: List[str] = field(default_factory=list)

    @property
    def elapsed(self) -> float:
        if not self.started_at:
            return 0.0
        end = self.finished_at or time.time()
        return round(end - self.started_at, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "platform": self.platform,
            "success": self.success,
            "exit_code": self.exit_code,
            "elapsed_seconds": self.elapsed,
            "error": self.error,
            "timed_out": self.timed_out,
        }


def platform_max_parallel(platform: str) -> int:
    """取某平台的并发上限。

    优先读环境变量 MEDIACRAWLER_PLATFORM_MAX_PARALLEL_<PLATFORM>，
    未设置则用 DEFAULT_PLATFORM_MAX_PARALLEL。
    """
    env_key = f"MEDIACRAWLER_PLATFORM_MAX_PARALLEL_{platform.upper()}"
    raw = os.getenv(env_key)
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return max(1, int(getattr(config, "DEFAULT_PLATFORM_MAX_PARALLEL", 1)))


def _tail(lines: List[str], keep: int = 20) -> List[str]:
    return [line for line in lines if line.strip()][-keep:]


async def run_single_platform(
    platform: str,
    extra_args: Optional[List[str]] = None,
    timeout: Optional[int] = None,
    keep_output_lines: int = 20,
    on_line=None,
) -> PlatformTaskResult:
    """
    以独立子进程运行单个平台。

    :param platform: 平台 code，如 xhs / wb / dy
    :param extra_args: 附加命令行参数，如 ["--keywords", "疫情"]
    :param timeout: 超时秒数，None 表示用 config.PLATFORM_TASK_TIMEOUT_SECONDS
    :param keep_output_lines: 结果里保留的输出尾部行数
    :param on_line: 可选的逐行回调 on_line(platform, line)
    """
    result = PlatformTaskResult(platform=platform)
    result.started_at = time.time()

    if timeout is None:
        timeout = int(getattr(config, "PLATFORM_TASK_TIMEOUT_SECONDS", 1800))

    cmd = [sys.executable, "main.py", "--platform", platform]
    cmd.extend(list(extra_args or []))

    popen_kwargs: Dict[str, Any] = {}
    if os.name != "nt":
        popen_kwargs["start_new_session"] = True

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(PROJECT_ROOT),
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
            **popen_kwargs,
        )
    except Exception as exc:
        result.error = f"启动失败: {exc}"
        result.finished_at = time.time()
        return result

    collected: List[str] = []

    async def _drain(stream):
        if stream is None:
            return
        while True:
            try:
                line = await stream.readline()
            except Exception:
                break
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            collected.append(text)
            if on_line:
                try:
                    on_line(platform, text)
                except Exception:
                    pass

    reader = asyncio.create_task(_drain(proc.stdout))

    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
        result.exit_code = proc.returncode
        result.success = proc.returncode == 0
        if not result.success:
            login_code = getattr(config, "LOGIN_FAILED_EXIT_CODE", 2)
            if proc.returncode == login_code:
                result.error = (
                    "登录失败：未能在超时前完成登录。并行场景下无法扫码，"
                    "请改用 cookie 登录或复用 browser_data 中已保存的登录态"
                )
            else:
                result.error = f"进程退出码 {proc.returncode}"
    except asyncio.TimeoutError:
        result.timed_out = True
        result.error = f"超过 {timeout} 秒未完成，已终止"
        _terminate_process(proc)
        try:
            await asyncio.wait_for(proc.wait(), timeout=15)
        except asyncio.TimeoutError:
            pass
        result.exit_code = proc.returncode
    except asyncio.CancelledError:
        # 被 fail_fast 取消：必须终止子进程，否则浏览器进程会遗留
        result.error = "因其他平台失败而被中止"
        _terminate_process(proc)
        try:
            await asyncio.wait_for(proc.wait(), timeout=10)
        except (asyncio.TimeoutError, Exception):
            pass
        reader.cancel()
        result.finished_at = time.time()
        result.stdout_tail = _tail(collected, keep_output_lines)
        raise
    finally:
        if not result.finished_at:
            try:
                await asyncio.wait_for(reader, timeout=10)
            except (asyncio.TimeoutError, Exception):
                reader.cancel()
            result.finished_at = time.time()
            result.stdout_tail = _tail(collected, keep_output_lines)

    return result


def _terminate_process(proc: asyncio.subprocess.Process) -> None:
    """终止进程组（含 Chromium 等子进程），避免超时后留下孤儿浏览器进程"""
    import signal

    try:
        if os.name != "nt":
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        else:
            proc.terminate()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


async def run_platforms_parallel(
    tasks: List[Dict[str, Any]],
    max_parallel: Optional[int] = None,
    timeout: Optional[int] = None,
    fail_fast: Optional[bool] = None,
    on_line=None,
    on_result=None,
) -> List[PlatformTaskResult]:
    """
    并行运行多个平台任务。

    :param tasks: 任务列表，每项形如
                  {"platform": "xhs", "args": ["--keywords", "疫情"], "timeout": 600}
    :param max_parallel: 全局并发上限，None 用 config.MAX_PARALLEL_PLATFORMS
    :param timeout: 单任务默认超时
    :param fail_fast: 某任务失败是否取消其余，None 用 config.PARALLEL_FAIL_FAST
    :param on_line: 逐行日志回调 on_line(platform, text)
    :param on_result: 单任务完成回调 on_result(PlatformTaskResult)
    :return: 结果列表（顺序与 tasks 一致）
    """
    if not tasks:
        return []

    if max_parallel is None:
        max_parallel = max(1, int(getattr(config, "MAX_PARALLEL_PLATFORMS", 3)))
    if fail_fast is None:
        fail_fast = bool(getattr(config, "PARALLEL_FAIL_FAST", False))

    # 全局并发闸门
    global_sem = asyncio.Semaphore(max_parallel)
    # 每平台并发闸门：默认 1，避免同平台争用同一个 user_data_dir
    platform_sems: Dict[str, asyncio.Semaphore] = {}
    for task in tasks:
        platform = task["platform"]
        if platform not in platform_sems:
            platform_sems[platform] = asyncio.Semaphore(platform_max_parallel(platform))

    results: List[Optional[PlatformTaskResult]] = [None] * len(tasks)
    # fail_fast 用：任一任务失败后，尚未取得闸门的任务直接跳过
    abort = asyncio.Event()
    worker_tasks: Dict[int, asyncio.Task] = {}

    async def _worker(index: int, task: Dict[str, Any]) -> PlatformTaskResult:
        platform = task["platform"]

        # 已失败且要求快速中止 -> 不再占用资源，直接标记取消
        if abort.is_set():
            return PlatformTaskResult(platform=platform, error="因其他平台失败而中止")

        async with global_sem:
            # 排队期间可能已被中止
            if abort.is_set():
                return PlatformTaskResult(platform=platform, error="因其他平台失败而中止")

            async with platform_sems[platform]:
                result = await run_single_platform(
                    platform=platform,
                    extra_args=task.get("args") or [],
                    # 不能用 task.get("timeout", timeout)：
                    # 键存在但值为 0 时会取到 0，导致 wait_for(0) 立刻超时杀掉子进程。
                    # 未指定超时的任务里 timeout 是 0（CLI 默认值），必须回落到全局值。
                    timeout=task.get("timeout") or timeout,
                    on_line=on_line,
                )

        results[index] = result
        if on_result:
            try:
                on_result(result)
            except Exception:
                pass

        if fail_fast and not result.success:
            abort.set()
            # 同时取消仍在运行的任务（不能只跳过未启动的，
            # 否则正在跑的子进程会继续占用资源、留下浏览器进程）
            for other_index, other_task in worker_tasks.items():
                if other_index != index and not other_task.done():
                    other_task.cancel()

        return result

    worker_tasks = {
        index: asyncio.ensure_future(_worker(index, task))
        for index, task in enumerate(tasks)
    }
    gathered = await asyncio.gather(*worker_tasks.values(), return_exceptions=True)

    final: List[PlatformTaskResult] = []
    for index, item in enumerate(gathered):
        platform = tasks[index]["platform"]
        if isinstance(item, PlatformTaskResult):
            final.append(item)
        elif isinstance(item, asyncio.CancelledError):
            # 区分「因其他平台失败而中止」与「外部调用方取消」
            reason = "因其他平台失败而中止" if abort.is_set() else "已取消"
            final.append(PlatformTaskResult(platform=platform, error=reason))
        elif isinstance(item, Exception):
            final.append(PlatformTaskResult(platform=platform, error=str(item)))
        else:
            final.append(PlatformTaskResult(platform=platform, error="未知错误"))

    return final

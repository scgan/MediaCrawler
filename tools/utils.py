# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/tools/utils.py
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


import argparse
import logging
import os
import signal
import socket
import time

from .crawler_util import *
from .slider_util import *
from .time_util import *


def init_loging_config():
    level = logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)s %(levelname)s (%(filename)s:%(lineno)d) - %(message)s",
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    _logger = logging.getLogger("MediaCrawler")
    _logger.setLevel(level)

    # Disable httpx INFO level logs
    logging.getLogger("httpx").setLevel(logging.WARNING)

    return _logger


logger = init_loging_config()


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _read_cmdline(pid: int) -> str:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return f.read().replace(b"\x00", b" ").decode("utf-8", errors="ignore")
    except OSError:
        return ""


def _terminate_process(pid: int, timeout_seconds: float = 3.0) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if not _pid_exists(pid):
            return
        time.sleep(0.2)

    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def _parse_chromium_singleton_lock(lock_path: str) -> tuple[str | None, int | None]:
    try:
        target = os.readlink(lock_path)
    except OSError:
        return None, None

    host, _, pid_text = target.rpartition("-")
    try:
        return host or None, int(pid_text)
    except ValueError:
        return host or None, None


def prepare_browser_user_data_dir(user_data_dir: str) -> None:
    """Prepare Chromium profile dir and clear stale locks left by old containers."""

    os.makedirs(user_data_dir, exist_ok=True)

    lock_path = os.path.join(user_data_dir, "SingletonLock")
    lock_host, lock_pid = _parse_chromium_singleton_lock(lock_path)
    current_host = socket.gethostname()

    if lock_pid and lock_host == current_host and _pid_exists(lock_pid):
        cmdline = _read_cmdline(lock_pid)
        if user_data_dir in cmdline:
            logger.warning(
                "[BrowserProfile] Chromium profile is still locked by pid %s, terminating it before relaunch.",
                lock_pid,
            )
            _terminate_process(lock_pid)
        else:
            logger.warning(
                "[BrowserProfile] Chromium profile lock references pid %s, but it does not look like this profile.",
                lock_pid,
            )

    # Locks from a previous container hostname or a dead Chromium process block relaunch.
    for name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        path = os.path.join(user_data_dir, name)
        try:
            if os.path.lexists(path):
                os.unlink(path)
                logger.warning("[BrowserProfile] Removed stale Chromium profile lock: %s", path)
        except OSError as exc:
            logger.warning("[BrowserProfile] Failed to remove Chromium profile lock %s: %s", path, exc)

def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')

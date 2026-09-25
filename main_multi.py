# -*- coding: utf-8 -*-
"""
多平台并行采集入口（CLI）。

用法
----
    # 多平台并行，共用同一批关键词
    python main_multi.py --platforms xhs,wb,dy --keywords "疫情,防控"

    # 从 JSON 文件加载任务（每平台可配不同参数）
    python main_multi.py --config tasks.json

    # 覆盖并发上限 / 超时
    python main_multi.py --platforms xhs,wb --max_parallel 2 --timeout 900

tasks.json 示例
---------------
    [
      {"platform": "xhs", "args": ["--keywords", "疫情", "--lt", "cookie", "--cookies", "web_session=xxx"]},
      {"platform": "wb",  "args": ["--keywords", "疫情"]},
      {"platform": "dy",  "args": ["--keywords", "疫情"], "timeout": 600}
    ]

设计说明
--------
每个平台一个独立 `main.py` 子进程：config 是模块级全局单例，
单进程内无法让两个平台各用一套 PLATFORM / KEYWORDS / COOKIES，
多进程是唯一稳妥的隔离方式。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from tools.platform_runner import (  # noqa: E402
    PlatformTaskResult,
    platform_max_parallel,
    run_platforms_parallel,
)

# 支持的平台，与 CrawlerFactory.CRAWLERS 保持一致
SUPPORTED_PLATFORMS = ("xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu")


def _split_platforms(raw: str) -> List[str]:
    items = [item.strip() for item in (raw or "").replace("，", ",").split(",")]
    return [item for item in items if item]


def _validate_platforms(platforms: List[str]) -> None:
    for platform in platforms:
        if platform not in SUPPORTED_PLATFORMS:
            raise SystemExit(
                f"不支持的平台: {platform!r}，可选: {', '.join(SUPPORTED_PLATFORMS)}"
            )


def build_tasks_from_cli(args: argparse.Namespace) -> List[Dict[str, Any]]:
    """由命令行参数构造任务列表（所有平台共用同一批参数）"""
    platforms = _split_platforms(args.platforms)
    if not platforms:
        raise SystemExit("请通过 --platforms 指定至少一个平台，或用 --config 加载任务文件")
    _validate_platforms(platforms)

    common: List[str] = []
    if args.keywords:
        common.extend(["--keywords", args.keywords])
    if args.lt:
        common.extend(["--lt", args.lt])
    if args.crawler_type:
        common.extend(["--type", args.crawler_type])
    if args.save_data_option:
        common.extend(["--save_data_option", args.save_data_option])
    if args.max_notes_count:
        common.extend(["--max_notes_count", str(args.max_notes_count)])
    if args.cookies:
        common.extend(["--cookies", args.cookies])
    common.extend(["--get_comment", "true" if args.get_comment else "false"])
    common.extend(["--get_sub_comment", "true" if args.get_sub_comment else "false"])
    common.extend(["--headless", "true" if args.headless else "false"])
    if args.start_time:
        common.extend(["--start_time", args.start_time])
    if args.end_time:
        common.extend(["--end_time", args.end_time])

    return [
        {"platform": platform, "args": list(common), "timeout": args.timeout}
        for platform in platforms
    ]


def load_tasks_from_file(path: str) -> List[Dict[str, Any]]:
    """从 JSON 文件加载任务列表"""
    file_path = Path(path)
    if not file_path.exists():
        raise SystemExit(f"任务文件不存在: {path}")

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"任务文件不是合法 JSON: {exc}")

    if isinstance(data, dict):
        data = data.get("tasks") or []
    if not isinstance(data, list) or not data:
        raise SystemExit("任务文件应包含非空的任务数组")

    # 这三个键有专门语义，其余键一律视为命令行参数名
    RESERVED = {"platform", "args", "timeout"}

    tasks: List[Dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict) or not item.get("platform"):
            raise SystemExit(f"任务缺少 platform 字段: {item}")
        platform = str(item["platform"]).strip()
        _validate_platforms([platform])

        args: List[str] = []

        # 1) 任务级命名字段：{"platform": "xhs", "keywords": "疫情", "cookies": "xxx"}
        #    这是最自然的写法，必须支持，否则参数会被静默丢弃
        for key, value in item.items():
            if key in RESERVED or value is None or value == "":
                continue
            if isinstance(value, bool):
                # 布尔开关：True 传 "true"，False 传 "false"
                args.extend([f"--{key}", "true" if value else "false"])
            else:
                args.extend([f"--{key}", str(value)])

        # 2) args 字段：列表形式 ["--keywords", "x"] 或对象形式 {"keywords": "x"}
        raw_args = item.get("args") or []
        if isinstance(raw_args, dict):
            for key, value in raw_args.items():
                args.extend([f"--{key}", str(value)])
        else:
            args.extend(str(part) for part in raw_args)

        tasks.append({
            "platform": platform,
            "args": args,
            "timeout": item.get("timeout"),
        })
    return tasks


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="MediaCrawler 多平台并行采集（不同平台并行，同一平台默认串行）"
    )
    parser.add_argument("--platforms", default="", help="平台列表，逗号分隔，如 xhs,wb,dy")
    parser.add_argument("--config", dest="config_file", default="", help="任务 JSON 文件路径")
    parser.add_argument("--keywords", default="", help="搜索关键词，逗号分隔（多平台共用）")
    parser.add_argument("--lt", default="", help="登录方式：qrcode / phone / cookie")
    parser.add_argument("--type", dest="crawler_type", default="", help="采集类型：search / detail / creator")
    parser.add_argument("--save_data_option", default="", help="保存方式：csv / json / jsonl / db / sqlite")
    parser.add_argument("--max_notes_count", type=int, default=0, help="每个平台采集条数")
    parser.add_argument("--cookies", default="", help="Cookie 串（多平台共用，通常应按平台分别配）")
    parser.add_argument("--get_comment", action="store_true", default=True, help="采集评论")
    parser.add_argument("--no_comment", dest="get_comment", action="store_false", help="不采集评论")
    parser.add_argument("--get_sub_comment", action="store_true", default=False, help="采集二级评论")
    parser.add_argument("--headless", action="store_true", default=False, help="无头模式")
    parser.add_argument("--start_time", default="", help="发布时间起始")
    parser.add_argument("--end_time", default="", help="发布时间截止")
    parser.add_argument(
        "--max_parallel", type=int, default=0,
        help=f"全局并发上限（默认读配置，当前 {getattr(config, 'MAX_PARALLEL_PLATFORMS', 3)}）",
    )
    parser.add_argument("--timeout", type=int, default=0, help="单平台超时秒数，0 表示用配置值")
    parser.add_argument("--fail_fast", action="store_true", default=None, help="某平台失败则中止其余")
    parser.add_argument("--quiet", action="store_true", help="不实时打印子进程输出")
    return parser.parse_args(argv)


async def async_main(args: argparse.Namespace) -> int:
    if args.config_file:
        tasks = load_tasks_from_file(args.config_file)
    else:
        tasks = build_tasks_from_cli(args)

    max_parallel = args.max_parallel or int(getattr(config, "MAX_PARALLEL_PLATFORMS", 3))
    timeout = args.timeout or int(getattr(config, "PLATFORM_TASK_TIMEOUT_SECONDS", 1800))

    platforms = [task["platform"] for task in tasks]
    print("=" * 72)
    print(f"准备并行采集 {len(tasks)} 个平台: {', '.join(platforms)}")
    print(f"全局并发上限 = {max_parallel}；单平台超时 = {timeout}s")
    print("每平台并发上限: " + ", ".join(
        f"{p}={platform_max_parallel(p)}" for p in dict.fromkeys(platforms)
    ))
    print("=" * 72)
    print("提示：并行场景下无法扫码，请确保已配置 cookie 登录或已保存登录态\n")

    if not args.quiet:
        def _on_line(platform: str, text: str) -> None:
            print(f"[{platform}] {text}", flush=True)
    else:
        _on_line = None

    def _on_result(result: PlatformTaskResult) -> None:
        flag = "✅" if result.success else "❌"
        print(
            f"{flag} [{result.platform}] 完成 耗时={result.elapsed}s "
            f"退出码={result.exit_code}"
            + (f" 错误={result.error}" if result.error else ""),
            flush=True,
        )

    results = await run_platforms_parallel(
        tasks=tasks,
        max_parallel=max_parallel,
        timeout=timeout,
        fail_fast=args.fail_fast,
        on_line=_on_line,
        on_result=_on_result,
    )

    print("\n" + "=" * 72)
    print("采集汇总")
    print("=" * 72)
    success_list = [r for r in results if r.success]
    failed_list = [r for r in results if not r.success]

    for result in results:
        status = "成功" if result.success else "失败"
        extra = ""
        if result.timed_out:
            extra = "（超时）"
        elif result.error:
            extra = f"（{result.error}）"
        print(f"  {result.platform:8s} {status:4s} 耗时 {result.elapsed:>7.2f}s{extra}")

    print(f"\n成功 {len(success_list)} 个，失败 {len(failed_list)} 个")

    if failed_list:
        print("\n失败明细：")
        for result in failed_list:
            print(f"  [{result.platform}] {result.error}")
            for line in result.stdout_tail[-5:]:
                print(f"      | {line}")
        return 1
    return 0


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(async_main(args))
    except KeyboardInterrupt:
        print("\n已中断")
        return 130


if __name__ == "__main__":
    sys.exit(main())

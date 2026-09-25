# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/tools/crawler_util.py
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


# -*- coding: utf-8 -*-
# @Author  : relakkes@gmail.com
# @Time    : 2023/12/2 12:53
# @Desc    : Crawler utility functions

import asyncio
import base64
import json
import random
import re
import urllib
import urllib.parse
from io import BytesIO
from typing import Dict, List, Optional, Tuple, cast

import httpx
from PIL import Image, ImageDraw, ImageShow
from playwright.async_api import BrowserContext, Cookie, Page

from . import utils
from .httpx_util import make_async_client


async def find_login_qrcode(page: Page, selector: str) -> str:
    """find login qrcode image from target selector"""
    try:
        elements = await page.wait_for_selector(
            selector=selector,
        )
        login_qrcode_img = str(await elements.get_property("src"))  # type: ignore
        if "http://" in login_qrcode_img or "https://" in login_qrcode_img:
            async with make_async_client(follow_redirects=True) as client:
                utils.logger.info(f"[find_login_qrcode] get qrcode by url:{login_qrcode_img}")
                resp = await client.get(login_qrcode_img, headers={"User-Agent": get_user_agent()})
                if resp.status_code == 200:
                    image_data = resp.content
                    base64_image = base64.b64encode(image_data).decode('utf-8')
                    return base64_image
                raise Exception(f"fetch login image url failed, response message:{resp.text}")
        return login_qrcode_img

    except Exception as e:
        print(e)
        return ""


async def find_qrcode_img_from_canvas(page: Page, canvas_selector: str) -> str:
    """
    find qrcode image from canvas element
    Args:
        page:
        canvas_selector:

    Returns:

    """

    # Wait for Canvas element to load
    canvas = await page.wait_for_selector(canvas_selector)

    # Take screenshot of Canvas element
    screenshot = await canvas.screenshot()

    # Convert screenshot to base64 format
    base64_image = base64.b64encode(screenshot).decode('utf-8')
    return base64_image


def show_qrcode(qr_code) -> None:  # type: ignore
    """parse base64 encode qrcode image and show it"""
    if "," in qr_code:
        qr_code = qr_code.split(",")[1]
    qr_code = base64.b64decode(qr_code)
    image = Image.open(BytesIO(qr_code))

    # Add a square border around the QR code and display it within the border to improve scanning accuracy.
    width, height = image.size
    new_image = Image.new('RGB', (width + 20, height + 20), color=(255, 255, 255))
    new_image.paste(image, (10, 10))
    draw = ImageDraw.Draw(new_image)
    draw.rectangle((0, 0, width + 19, height + 19), outline=(0, 0, 0), width=1)
    del ImageShow.UnixViewer.options["save_all"]
    new_image.show()


def get_user_agent() -> str:
    ua_list = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.5112.79 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.5060.53 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.84 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.5112.79 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.5060.53 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.4844.84 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.5112.79 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.5060.53 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.4844.84 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.5112.79 Safari/537.36"
    ]
    return random.choice(ua_list)


def get_mobile_user_agent() -> str:
    ua_list = [
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1"
    ]
    return random.choice(ua_list)


def convert_cookies(cookies: Optional[List[Cookie]]) -> Tuple[str, Dict]:
    if not cookies:
        return "", {}
    cookies_str = ";".join([f"{cookie.get('name')}={cookie.get('value')}" for cookie in cookies])
    cookie_dict = dict()
    for cookie in cookies:
        cookie_dict[cookie.get('name')] = cookie.get('value')
    return cookies_str, cookie_dict


async def convert_browser_context_cookies(
    browser_context: BrowserContext, urls: Optional[List[str]] = None
) -> Tuple[str, Dict]:
    cookies = (
        await browser_context.cookies(urls=urls)
        if urls
        else await browser_context.cookies()
    )
    return convert_cookies(cookies)


def convert_str_cookie_to_dict(cookie_str: str) -> Dict:
    cookie_dict: Dict[str, str] = dict()
    if not cookie_str:
        return cookie_dict
    for cookie in cookie_str.split(";"):
        cookie = cookie.strip()
        if not cookie:
            continue
        cookie_list = cookie.split("=")
        if len(cookie_list) != 2:
            continue
        cookie_value = cookie_list[1]
        if isinstance(cookie_value, list):
            cookie_value = "".join(cookie_value)
        cookie_dict[cookie_list[0]] = cookie_value
    return cookie_dict


def match_interact_info_count(count_str: str) -> int:
    if not count_str:
        return 0

    match = re.search(r'\d+', count_str)
    if match:
        number = match.group()
        return int(number)
    else:
        return 0


def format_proxy_info(ip_proxy_info) -> Tuple[Optional[Dict], Optional[str]]:
    """format proxy info for playwright and httpx"""
    # fix circular import issue
    from proxy.proxy_ip_pool import IpInfoModel
    ip_proxy_info = cast(IpInfoModel, ip_proxy_info)

    # Playwright proxy server should be in format "host:port" without protocol prefix
    server = f"{ip_proxy_info.ip}:{ip_proxy_info.port}"
    
    playwright_proxy = {
        "server": server,
    }
    
    # Only add username and password if they are not empty
    if ip_proxy_info.user and ip_proxy_info.password:
        playwright_proxy["username"] = ip_proxy_info.user
        playwright_proxy["password"] = ip_proxy_info.password
    
    # httpx 0.28.1 requires passing proxy URL string directly, not a dictionary
    if ip_proxy_info.user and ip_proxy_info.password:
        httpx_proxy = f"http://{ip_proxy_info.user}:{ip_proxy_info.password}@{ip_proxy_info.ip}:{ip_proxy_info.port}"
    else:
        httpx_proxy = f"http://{ip_proxy_info.ip}:{ip_proxy_info.port}"
    return playwright_proxy, httpx_proxy


def extract_text_from_html(html: str) -> str:
    """Extract text from HTML, removing all tags."""
    if not html:
        return ""

    # Remove script and style elements
    clean_html = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=re.DOTALL)
    # Remove all other tags
    clean_text = re.sub(r'<[^>]+>', '', clean_html).strip()
    return clean_text

def extract_url_params_to_dict(url: str) -> Dict:
    """Extract URL parameters to dict"""
    url_params_dict = dict()
    if not url:
        return url_params_dict
    parsed_url = urllib.parse.urlparse(url)
    url_params_dict = dict(urllib.parse.parse_qsl(parsed_url.query))
    return url_params_dict


def build_browser_args() -> list:
    """
    构造 Chromium 启动参数。

    为什么需要这个：
        标准模式（chromium.launch）默认不传 args，Chromium 会用 /dev/shm 作共享内存。
        Docker 默认 /dev/shm 仅 64MB，本项目 compose 设了 2GB —— 多平台并行时
        多个 Chromium 争抢，会触发渲染进程崩溃（Target crashed），
        表现为莫名其妙的采集失败。
        CDP 模式本来就带 --disable-dev-shm-usage（见 tools/browser_launcher.py），
        这里补上标准模式缺失的部分。
    """
    import config  # 延迟导入，避免模块加载期循环依赖

    args = []
    if getattr(config, "DISABLE_DEV_SHM_USAGE", True):
        args.append("--disable-dev-shm-usage")
        args.append("--no-sandbox")
        args.append("--disable-gpu")

    extra = (getattr(config, "BROWSER_EXTRA_ARGS", "") or "").strip()
    if extra:
        for item in extra.replace("，", ",").split(","):
            item = item.strip()
            if item and item not in args:
                args.append(item)
    return args


def set_default_navigation_timeout(browser_context) -> None:
    """
    统一设置浏览器上下文的导航超时（毫秒）。

    Playwright 默认导航超时仅 30 秒，且默认等待 load 事件（需等所有图片/视频/脚本
    加载完成）。快手 / 抖音等重资源首页在容器或弱网环境下经常触发：
        playwright TimeoutError: Page.goto: Timeout 30000ms exceeded.
    这里按 config.PAGE_NAVIGATION_TIMEOUT 统一放宽；在 context 级设置一次，
    即可覆盖该 context 下所有页面的 goto，无需逐个调用点修改。
    """
    import config  # 延迟导入，避免模块加载期的循环依赖

    try:
        timeout_ms = max(1, int(config.PAGE_NAVIGATION_TIMEOUT)) * 1000
    except (TypeError, ValueError):
        timeout_ms = 60000
    browser_context.set_default_navigation_timeout(timeout_ms)
    browser_context.set_default_timeout(timeout_ms)


async def safe_goto(page, url, wait_until=None, timeout_ms=None, retries=2) -> bool:
    """
    导航到指定 URL，容忍 ERR_ABORTED 这类「导航被中断但页面实际已可用」的错误。

    背景：登录页（如微博 passport.weibo.com/sso/signin）在检测到已有登录态时
    会立即重定向，原导航被新导航打断，Playwright 抛出：
        playwright._impl._errors.Error: Page.goto: net::ERR_ABORTED
    此时页面其实已到达目标，直接抛异常会误判为失败。
    注意这与 TimeoutError 性质不同：超时是「等太久」，调大超时有效；
    ERR_ABORTED 是「被打断」，加超时无效，需要容错处理。

    :param page: Playwright Page 对象
    :param url: 目标 URL
    :param wait_until: 等待策略，默认取 config.PAGE_WAIT_UNTIL
    :param timeout_ms: 导航超时（毫秒），默认取 config.PAGE_NAVIGATION_TIMEOUT
    :param retries: ERR_ABORTED 时页面不可用情况下的重试次数
    :return: 导航是否成功（ERR_ABORTED 但页面可用时返回 True）
    """
    import config  # 延迟导入，避免模块加载期循环依赖

    if wait_until is None:
        wait_until = getattr(config, "PAGE_WAIT_UNTIL", "domcontentloaded")
    if timeout_ms is None:
        timeout_ms = max(1, int(getattr(config, "PAGE_NAVIGATION_TIMEOUT", 60))) * 1000

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            return True
        except Exception as exc:  # noqa: BLE001 - 需要按消息区分可恢复错误
            last_error = exc
            message = str(exc) or ""
            exc_msg = getattr(exc, "message", "") or ""
            combined = f"{message} {exc_msg}"

            # 仅对「导航被中断」做容错：确认页面仍可用即视为成功
            if "ERR_ABORTED" in combined:
                try:
                    if not page.is_closed() and page.url:
                        return True
                except Exception:
                    pass
                if attempt < retries:
                    await asyncio.sleep(1)
                    continue
            # 其余错误（含 TimeoutError）原样抛出，避免掩盖真实问题
            raise
    raise last_error

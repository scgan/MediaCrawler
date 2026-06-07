FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DISPLAY=:99 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    MEDIACRAWLER_HEADLESS=false \
    MEDIACRAWLER_ENABLE_CDP=false \
    MEDIACRAWLER_CDP_CONNECT_EXISTING=false \
    MEDIACRAWLER_CDP_HEADLESS=false \
    MEDIACRAWLER_BROWSER_LAUNCH_TIMEOUT=90

WORKDIR /app

# 系统依赖：
# - xvfb/fluxbox/x11vnc/novnc/websockify：用于服务器中显示浏览器窗口
# - fonts：避免中文页面/二维码页面显示异常
# - nodejs/npm：抖音、知乎等平台依赖 Node.js
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    nodejs \
    npm \
    xvfb \
    fluxbox \
    x11vnc \
    novnc \
    websockify \
    fonts-noto-cjk \
    fonts-wqy-zenhei \
    libnss3 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen || uv sync

COPY . .

# 安装 Playwright Chromium
RUN uv run playwright install chromium

# 准备目录
RUN mkdir -p /app/browser_data /app/data && chmod -R 777 /app/browser_data /app/data

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8080 6080 5900

CMD ["/entrypoint.sh"]
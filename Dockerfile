FROM python:3.11-slim-bookworm

ARG APT_MIRROR=http://mirrors.aliyun.com/debian
ARG APT_SECURITY_MIRROR=http://mirrors.aliyun.com/debian-security
ARG PYPI_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG NPM_REGISTRY=https://registry.npmmirror.com
ARG PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:${PATH}" \
    UV_CACHE_DIR=/tmp/uv-cache \
    UV_LINK_MODE=copy \
    PIP_INDEX_URL=${PYPI_INDEX_URL} \
    UV_INDEX_URL=${PYPI_INDEX_URL} \
    npm_config_registry=${NPM_REGISTRY} \
    PLAYWRIGHT_DOWNLOAD_HOST=${PLAYWRIGHT_DOWNLOAD_HOST} \
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
RUN set -eux; \
    sed -i \
      -e "s|http://deb.debian.org/debian-security|${APT_SECURITY_MIRROR}|g" \
      -e "s|http://security.debian.org/debian-security|${APT_SECURITY_MIRROR}|g" \
      -e "s|http://deb.debian.org/debian|${APT_MIRROR}|g" \
      /etc/apt/sources.list.d/debian.sources; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    tini \
    nodejs \
    npm \
    xvfb \
    x11-utils \
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
    libgl1 \
    libglib2.0-0 \
    libxshmfence1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libgtk-3-0; \
    rm -rf /var/lib/apt/lists/*

# 安装 uv
RUN pip install --no-cache-dir -i "${PYPI_INDEX_URL}" uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen || uv sync

COPY . .

# 安装 Playwright Chromium
RUN python -m playwright install chromium

# 准备目录
RUN mkdir -p /app/browser_data /app/data /tmp/uv-cache && chmod -R 777 /app/browser_data /app/data /tmp/uv-cache

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8080 6080 5900

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/api/health || exit 1

ENTRYPOINT ["tini", "--"]
CMD ["/entrypoint.sh"]

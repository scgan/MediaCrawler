FROM python:3.11-bookworm
WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV UV_PYTHON=/usr/local/bin/python
ENV UV_PYTHON_DOWNLOADS=never

# ===== pip / npm / playwright 镜像 =====
ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn
ENV NPM_CONFIG_REGISTRY=https://registry.npmmirror.com
ENV PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright/
ENV PLAYWRIGHT_CDN_MIRROR=https://npmmirror.com/mirrors/playwright/

# ===== 1) 换 APT 源 =====
RUN set -eux; \
    FILES="$(find /etc/apt -type f \( -name '*.list' -o -name '*.sources' \) 2>/dev/null)"; \
    if [ -n "$FILES" ]; then \
      echo "$FILES" | xargs -I{} sed -i \
        -e 's|deb\.debian\.org|mirrors.aliyun.com|g' \
        -e 's|security\.debian\.org|mirrors.aliyun.com|g' {} + 2>/dev/null || true; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        # 基础工具
        curl ca-certificates gnupg wget \
        # OpenCV 所需图形库
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender-dev \
        libgl1-mesa-glx \
        libgomp1 \
        # 图片处理库
        libjpeg-dev \
        libpng-dev \
        libtiff-dev \
        libopenexr-dev \
        libgstreamer1.0-0 \
        libgstreamer-plugins-base1.0-0 \
        # Playwright 运行时依赖
        libnss3 \
        libnspr4 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libdrm2 \
        libdbus-1-3 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxrandr2 \
        libgbm1 \
        libasound2 \
        libpango-1.0-0 \
        libcairo2 \
        libatspi2.0-0 \
        libwayland-client0 \
        libx11-6 \
        libxcb1 \
        libx11-xcb1 \
        libxshmfence1 \
        libgtk-3-0 \
        # 字体
        fonts-noto-cjk \
        fonts-wqy-zenhei \
        fonts-liberation \
        fonts-unifont \
        fonts-dejavu-core \
        fonts-freefont-ttf \
        # 构建/开发头文件
        build-essential \
        python3-dev \
        libxml2-dev \
        libxslt1-dev \
        zlib1g-dev \
        libfreetype6-dev \
        pkg-config \
        # node/npm
        nodejs \
        npm \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ===== 2) npm 镜像 =====
RUN npm config set registry "${NPM_CONFIG_REGISTRY}"

# ===== 3) 项目声明文件 =====
COPY pyproject.toml uv.lock* requirements.txt* ./

# ===== 4) 装 uv =====
RUN pip install --no-cache-dir uv -i "${PIP_INDEX_URL}" --trusted-host "${PIP_TRUSTED_HOST}"

# ===== 5) 依赖 =====
RUN if [ -f uv.lock ]; then \
        uv sync --frozen --python /usr/local/bin/python; \
    elif [ -f requirements.txt ]; then \
        pip install --no-cache-dir -r requirements.txt -i "${PIP_INDEX_URL}" --trusted-host "${PIP_TRUSTED_HOST}"; \
    else \
        uv sync --python /usr/local/bin/python; \
    fi

# ===== 6) Playwright =====
# 如果你的依赖里还没带 playwright，先确保装上
RUN uv run --python /usr/local/bin/python pip install -i "${PIP_INDEX_URL}" --trusted-host "${PIP_TRUSTED_HOST}" playwright

# 只下载 chromium，不触发 --with-deps 的 apt 分支
RUN PLAYWRIGHT_DOWNLOAD_HOST="${PLAYWRIGHT_DOWNLOAD_HOST}" \
    PLAYWRIGHT_CDN_MIRROR="${PLAYWRIGHT_CDN_MIRROR}" \
    uv run --python /usr/local/bin/python playwright install chromium

# ===== 7) 验证 OpenCV 安装 =====
RUN uv run --python /usr/local/bin/python python -c "import cv2; print(f'OpenCV version: {cv2.__version__}')"

# ===== 8) 收尾 =====
COPY . .
RUN mkdir -p /app/data /app/logs /app/cache /app/browser_data

EXPOSE 8080
CMD ["uv", "run", "--python", "/usr/local/bin/python", \
     "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
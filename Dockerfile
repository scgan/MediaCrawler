FROM python:3.11
WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV UV_PYTHON=/usr/local/bin/python
ENV UV_PYTHON_DOWNLOADS=never

# 设置 pip 国内镜像 (使用清华源)
ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn

# 设置 npm 国内镜像
ENV NPM_CONFIG_REGISTRY=https://registry.npmmirror.com

# 设置 Playwright 国内镜像
ENV PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright/
ENV PLAYWRIGHT_CDN_MIRROR=https://npmmirror.com/mirrors/playwright/

# 1. 更换 apt-get 源为阿里云镜像
# 先更新并安装必要的包，这会初始化 apt 配置
RUN set -eux; \
    # 确保 apt 工作正常，并尝试创建/更新源列表
    apt-get update || (mkdir -p /etc/apt/sources.list.d && touch /etc/apt/sources.list && apt-get update); \
    # 安装 sed 工具，用于后续的替换
    apt-get install -y --no-install-recommends sed; \
    # 现在执行替换操作，并再次更新
    sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list && \
    sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list; \
    apt-get update; \
    # 安装其他系统依赖
    apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        fonts-noto-cjk \
        fonts-wqy-zenhei \
        # 添加 Playwright 所需的依赖
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
        libxext6 \
        libxshmfence1 \
        libglib2.0-0 \
        libgtk-3-0 \
        # 字体
        fonts-liberation \
        fonts-unifont \
        fonts-dejavu-core \
        fonts-freefont-ttf \
        # 其他必要的工具
        wget \
        xdg-utils \
        # 构建依赖
        build-essential \
        python3-dev \
        libxml2-dev \
        libxslt1-dev \
        zlib1g-dev \
        libjpeg-dev \
        libpng-dev \
        libfreetype6-dev \
        pkg-config \
        nodejs \
        npm \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 2. 设置 npm 国内镜像
RUN npm config set registry ${NPM_CONFIG_REGISTRY}

COPY pyproject.toml uv.lock* requirements.txt* ./

# 3. 使用国内镜像安装 uv
RUN pip install --no-cache-dir uv -i ${PIP_INDEX_URL} --trusted-host ${PIP_TRUSTED_HOST}

# 4. 设置 uv 国内镜像
ENV UV_INDEX_URL=${PIP_INDEX_URL}
ENV UV_TRUSTED_HOSTS=${PIP_TRUSTED_HOST}

# 5. 安装依赖
RUN if [ -f "uv.lock" ]; then \
        uv sync --frozen --python /usr/local/bin/python; \
    elif [ -f "requirements.txt" ]; then \
        pip install --no-cache-dir -r requirements.txt; \
    else \
        uv sync --python /usr/local/bin/python; \
    fi

# 6. 安装 Playwright 浏览器（使用国内镜像）
# 先安装 playwright
RUN uv run --python /usr/local/bin/python pip install playwright
# 然后安装浏览器，跳过系统依赖检查
RUN PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 \
    uv run --python /usr/local/bin/python playwright install --skip-system-deps-check chromium

# 7. 验证安装
RUN uv run --python /usr/local/bin/python playwright --version && \
    uv run --python /usr/local/bin/python playwright install --list

COPY . .
RUN mkdir -p /app/data /app/logs /app/cache /app/browser_data
EXPOSE 8080
CMD ["uv", "run", "--python", "/usr/local/bin/python", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
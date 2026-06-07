FROM python:3.11-bookworm

WORKDIR /app

# 环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV UV_PYTHON=/usr/local/bin/python
ENV UV_PYTHON_DOWNLOADS=never
# 设置 pip 国内镜像
ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn
# 设置 npm 国内镜像
ENV NPM_CONFIG_REGISTRY=https://registry.npmmirror.com
# 设置 Playwright 国内镜像
ENV PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright/
ENV PLAYWRIGHT_CDN_MIRROR=https://npmmirror.com/mirrors/playwright/

# 1. 更换 apt-get 源为阿里云镜像
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list && \
    sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        fonts-noto-cjk \
        fonts-wqy-zenhei \
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
RUN npm config set registry https://registry.npmmirror.com

COPY pyproject.toml uv.lock* requirements.txt* ./

# 3. 使用国内镜像安装 uv
RUN pip install --no-cache-dir uv -i https://pypi.tuna.tsinghua.edu.cn/simple

# 4. 设置 uv 国内镜像
ENV UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV UV_TRUSTED_HOSTS=pypi.tuna.tsinghua.edu.cn

# 5. 安装依赖
RUN if [ -f "uv.lock" ]; then \
        uv sync --frozen --python /usr/local/bin/python; \
    elif [ -f "requirements.txt" ]; then \
        pip install --no-cache-dir -r requirements.txt; \
    else \
        uv sync --python /usr/local/bin/python; \
    fi

# 6. 安装 Playwright 浏览器（使用国内镜像）
RUN PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright/ \
    PLAYWRIGHT_CDN_MIRROR=https://npmmirror.com/mirrors/playwright/ \
    uv run --python /usr/local/bin/python playwright install --with-deps chromium

COPY . .

RUN mkdir -p /app/data /app/logs /app/cache /app/browser_data

EXPOSE 8080

CMD ["uv", "run", "--python", "/usr/local/bin/python", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
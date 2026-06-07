FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1

# 安装 Node.js，部分平台签名逻辑可能需要 Node >= 16
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        fonts-noto-cjk \
        fonts-wqy-zenhei \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖文件，利用 Docker 缓存
COPY pyproject.toml uv.lock* requirements.txt* ./

# 安装 uv
RUN pip install --no-cache-dir uv

# 优先使用 uv sync；如果没有 uv.lock，也可以 fallback 到 pip
RUN if [ -f "uv.lock" ]; then \
        uv sync --frozen; \
    elif [ -f "requirements.txt" ]; then \
        pip install --no-cache-dir -r requirements.txt; \
    else \
        uv sync; \
    fi

# 复制项目代码
COPY . .

# 确保数据目录存在
RUN mkdir -p /app/data /app/logs /app/cache /app/browser_data

EXPOSE 8080

CMD ["uv", "run", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
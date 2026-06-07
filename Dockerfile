FROM docker.1ms.run/library/python:3.11-bookworm

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV UV_PYTHON=/usr/local/bin/python
ENV UV_PYTHON_DOWNLOADS=never

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

COPY pyproject.toml uv.lock* requirements.txt* ./

RUN pip install --no-cache-dir uv

RUN if [ -f "uv.lock" ]; then \
        uv sync --frozen --python /usr/local/bin/python; \
    elif [ -f "requirements.txt" ]; then \
        pip install --no-cache-dir -r requirements.txt; \
    else \
        uv sync --python /usr/local/bin/python; \
    fi

# 安装 Playwright 浏览器及系统依赖
RUN uv run --python /usr/local/bin/python playwright install --with-deps chromium

COPY . .

RUN mkdir -p /app/data /app/logs /app/cache /app/browser_data

EXPOSE 8080

CMD ["uv", "run", "--python", "/usr/local/bin/python", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
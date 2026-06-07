FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV UV_PYTHON=/usr/bin/python3
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
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock* requirements.txt* ./

RUN pip install --no-cache-dir uv

RUN if [ -f "uv.lock" ]; then \
        uv sync --frozen --python /usr/bin/python3; \
    elif [ -f "requirements.txt" ]; then \
        pip install --no-cache-dir -r requirements.txt; \
    else \
        uv sync --python /usr/bin/python3; \
    fi

COPY . .

RUN mkdir -p /app/data /app/logs /app/cache /app/browser_data

EXPOSE 8080

CMD ["uv", "run", "--python", "/usr/bin/python3", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
FROM python:3.12-slim AS build
WORKDIR /build
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PRODUCTION=true \
    DATABASE_DIR=/app/database
WORKDIR /app

RUN groupadd --gid 10001 verifynews \
    && useradd --uid 10001 --gid 10001 --create-home verifynews \
    && install -d -o 10001 -g 10001 -m 0700 /app/database
COPY requirements.txt .
RUN --mount=type=bind,from=build,source=/wheels,target=/wheels \
    pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt

COPY backend/ ./backend/
COPY frontend/ ./frontend/
USER 10001:10001

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
  CMD ["python", "-c", "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3).close()"]
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--limit-concurrency", "32"]

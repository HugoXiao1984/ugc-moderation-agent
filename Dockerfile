# Backend container for ECS Fargate.
# Runs the FastAPI app (backend.api:app). Agent编排仍由 AgentCore Runtime 承载，
# 此容器只负责 HTTP 入口、视频/批量任务编排和聚合。
FROM public.ecr.aws/docker/library/python:3.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ffmpeg 给视频抽帧 fallback 用（CI 抽帧失败时的兜底路径）。
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml requirements.txt ./

# 直接装基础 + api extra；不用 uv，简单稳。
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install \
        "fastapi>=0.115.0" \
        "uvicorn[standard]>=0.32.0" \
        "python-multipart>=0.0.12"

COPY src ./src
COPY policies_scripts ./policies_scripts
COPY backend ./backend

ENV PYTHONPATH=/app/src:/app

EXPOSE 8000

# 单 worker：FastAPI BackgroundTasks 把视频任务放进同进程的 asyncio loop，
# 多 worker 会让进度字典各自独立，前端轮询拿不到。
CMD ["uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

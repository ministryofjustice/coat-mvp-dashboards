FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY cronjobs/showback_preload_cache/requirements.txt ./requirements.txt

RUN pip install -r requirements.txt

RUN groupadd --gid 1051 appgroup \
    && useradd --uid 1051 --gid appgroup --create-home appuser

COPY --chown=appuser:appgroup cronjobs/showback_preload_cache/ ./

USER 1051:1051

ENTRYPOINT ["python", "main.py"]
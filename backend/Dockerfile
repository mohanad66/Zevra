# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Miyar Trading — Django API container
# Multistage build so the runtime image ships no compilers or dev tooling.
# ---------------------------------------------------------------------------

FROM python:3.12-slim AS build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Dependencies first so layer cache is reused until requirements.txt changes.
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --prefix=/install -r requirements.txt


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_ENV=production \
    DJANGO_DEBUG=0

WORKDIR /app

# Runtime libs needed by wheels already baked into them; add only essentials.
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY --from=build /install /usr/local

# non-root runtime user
RUN addgroup --system --gid 10001 app && \
    adduser --system --uid 10001 --ingroup app --home /app app

COPY --chown=app:app . .

RUN mkdir -p /app/staticfiles /app/media && chown -R app:app /app/staticfiles /app/media

USER app

EXPOSE 8000
ENTRYPOINT ["/app/docker-entrypoint.sh"]
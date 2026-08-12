FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/tmp

WORKDIR /app

# Non-root runtime user. UID 10001 is deliberately non-colliding.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin aegis \
    && mkdir -p /models \
    && chown -R aegis:aegis /app /models

# Install dependencies first (layered cache; deps change less often than code).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code + DB migrations.
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .

USER aegis
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health')"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

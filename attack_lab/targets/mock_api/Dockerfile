FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin mockapi

COPY main.py /app/main.py
RUN pip install --no-cache-dir fastapi uvicorn pydantic==2.* --quiet \
    && chown -R mockapi:mockapi /app

USER mockapi
EXPOSE 8100
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8100"]

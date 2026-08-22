FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

COPY config.py .
COPY common ./common
COPY src ./src

ENTRYPOINT ["python", "-m", "src.fetch"]

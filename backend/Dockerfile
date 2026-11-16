FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including OpenJDK for LanguageTool
RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-17-jre-headless \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src src

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

EXPOSE 8000

ENV QIFREY_DB_PATH=/data/qifrey.db
ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "qifrey.main:app", "--host", "0.0.0.0", "--port", "8000"]

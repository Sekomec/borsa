# syntax=docker/dockerfile:1

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.docker.txt /app/requirements.txt

RUN pip install --upgrade pip && pip install -r /app/requirements.txt


FROM base AS development
COPY . /app
EXPOSE 8000


FROM base AS production
COPY . /app
EXPOSE 8000


"""
QuantEdge AI — Celery application
"""

from __future__ import annotations

from celery import Celery

from app.core.config import settings


def _redis_broker_url() -> str:
    # settings.REDIS_URL is typically redis://host:port/db
    return settings.REDIS_URL


celery_app = Celery(
    "quantedge",
    broker=_redis_broker_url(),
    backend=_redis_broker_url(),
    include=[
        "app.tasks.data_tasks",
        "app.tasks.prediction_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


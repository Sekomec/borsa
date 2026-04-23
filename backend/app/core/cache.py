"""
QuantEdge AI — Redis Cache Manager
=================================
Lightweight async cache wrapper used across the backend.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any, Optional

import structlog

from app.core.config import settings

logger = structlog.get_logger()


class CacheNamespace(StrEnum):
    MARKET_DATA = "market"
    OHLCV = "ohlcv"
    STOCK_INFO = "stock_info"
    SENTIMENT = "sentiment"
    NEWS = "news"
    MACRO = "macro"
    FUNDAMENTAL = "fundamental"
    PREDICTION = "prediction"
    FEATURES = "features"


class CacheManager:
    def __init__(self, prefix: str = "quantedge"):
        self.prefix = prefix
        self._redis = None

    def _make_key(self, namespace: str, key: str) -> str:
        return f"{self.prefix}:{namespace}:{key}"

    def is_connected(self) -> bool:
        return self._redis is not None

    async def connect(self) -> None:
        if self._redis is not None:
            return
        try:
            import redis.asyncio as redis  # type: ignore

            self._redis = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
            await self._redis.ping()
        except Exception as e:
            logger.warning("Redis bağlantısı kurulamadı. Cache devre dışı.", error=str(e))
            self._redis = None

    async def disconnect(self) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.close()
        except Exception:
            pass
        finally:
            self._redis = None

    async def get(self, namespace: str, key: str) -> Optional[Any]:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(self._make_key(namespace, key))
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as e:
            logger.debug("Cache get hatası.", namespace=namespace, key=key, error=str(e))
            return None

    async def set(self, namespace: str, key: str, value: Any, ttl: int = 300) -> None:
        if self._redis is None:
            return
        try:
            payload = json.dumps(value, default=str)
            await self._redis.set(self._make_key(namespace, key), payload, ex=ttl)
        except Exception as e:
            logger.debug("Cache set hatası.", namespace=namespace, key=key, error=str(e))


cache_manager = CacheManager()


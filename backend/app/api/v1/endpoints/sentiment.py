"""
Sentiment endpoints
"""

from __future__ import annotations

from fastapi import APIRouter

from app.services.data_fetchers.sentiment import sentiment_service

router = APIRouter()


@router.get("/{ticker}")
async def get_sentiment(ticker: str):
    ticker = ticker.strip().upper()
    return await sentiment_service.get_aggregated_sentiment(ticker)


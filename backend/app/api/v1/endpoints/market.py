"""
Market data endpoints
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.services.data_fetchers.market_data import market_data_service

router = APIRouter()

VALID_TIMEFRAMES = {"1d", "1h", "5m", "1w", "1mo"}


@router.get("/{ticker}/ohlcv")
async def get_ohlcv(
    ticker: str,
    timeframe: str = Query(default="1d"),
    limit: int = Query(default=365, ge=1, le=5000),
):
    ticker = ticker.strip().upper()
    timeframe = timeframe.strip()
    if timeframe not in VALID_TIMEFRAMES:
        raise HTTPException(status_code=400, detail="Geçersiz timeframe.")

    data = await market_data_service.get_ohlcv(ticker, timeframe=timeframe, limit=limit)
    if not data:
        raise HTTPException(status_code=404, detail="Veri bulunamadı.")

    return {"ticker": ticker, "timeframe": timeframe, "bars": len(data), "data": data}


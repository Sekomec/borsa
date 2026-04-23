"""
QuantEdge AI — Hisse Tahmin API Endpoint'leri
===============================================
Ana tahmin endpoint'i. ML motoru (Bölüm 3) ile entegre olur.
"""

from datetime import datetime
from typing import List, Optional

import structlog
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from fastapi.responses import ORJSONResponse

from app.models.schemas import PredictionRequest, PredictionResponse
from app.core.cache import cache_manager, CacheNamespace
from app.services.data_fetchers.market_data import market_data_service
from app.services.data_fetchers.macro import macro_service
from app.services.data_fetchers.sentiment import sentiment_service
from app.services.data_fetchers.fundamental import fundamental_service
from app.services.analysis.technical import technical_service

logger = structlog.get_logger()
router = APIRouter()

DISCLAIMER = (
    "⚠️ Bu tahminler istatistiksel modellerden üretilmekte olup %100 doğruluğu garanti edilmez. "
    "Yatırım tavsiyesi değildir. Finansal kararlarınızı lisanslı danışmanlarla alınız."
)

VALID_TIMEFRAMES = ["1d", "1w", "1mo", "3mo", "1y"]


@router.get("/{ticker}/info")
async def get_stock_info(ticker: str):
    ticker = ticker.strip().upper()
    return await market_data_service.get_stock_info(ticker)


@router.get("/{ticker}/quote")
async def get_quote(ticker: str):
    ticker = ticker.strip().upper()
    return await market_data_service.get_current_price(ticker)


@router.get("/{ticker}/technical")
async def get_technical(ticker: str, timeframe: str = Query(default="1d")):
    ticker = ticker.strip().upper()
    if timeframe not in ["1d", "1h", "5m", "1w", "1mo"]:
        raise HTTPException(status_code=400, detail="Geçersiz timeframe.")
    ohlcv = await market_data_service.get_ohlcv(ticker, timeframe=timeframe, limit=365)
    if not ohlcv:
        raise HTTPException(status_code=404, detail="Veri bulunamadı.")
    return technical_service.analyze(ohlcv, timeframe=timeframe)


@router.get("/{ticker}/fundamental")
async def get_fundamental(ticker: str):
    ticker = ticker.strip().upper()
    return await fundamental_service.get_comprehensive_fundamental(ticker)


@router.post("/predict", response_model=None)
async def predict_stock(
    request: PredictionRequest,
    background_tasks: BackgroundTasks,
):
    """
    Hisse senedi fiyat tahmini.

    Ensemble modeli kullanarak seçilen timeframe için:
    - Fiyat tahmini (nokta + güven aralığı)
    - Yön tahmini (up/down/sideways)
    - Teknik, sentiment, fundamental, makro sinyal özeti

    ⚠️ Yatırım tavsiyesi değildir.
    """
    ticker = request.ticker
    timeframe = request.timeframe

    # Cache kontrolü
    cache_key = f"{ticker}:{timeframe}:prediction"
    cached = await cache_manager.get(CacheNamespace.PREDICTION, cache_key)
    if cached:
        logger.debug("Tahmin cache'den döndürüldü.", ticker=ticker, timeframe=timeframe)
        return cached

    logger.info("Tahmin hesaplanıyor.", ticker=ticker, timeframe=timeframe)

    # 1. Tüm veri kaynaklarını paralel çek
    import asyncio
    ohlcv_task = market_data_service.get_ohlcv(ticker, "1d", 365)
    stock_info_task = market_data_service.get_stock_info(ticker)
    current_price_task = market_data_service.get_current_price(ticker)
    macro_task = macro_service.get_full_macro_context() if request.include_macro else None
    sentiment_task = sentiment_service.get_aggregated_sentiment(ticker) if request.include_sentiment else None
    fundamental_task = fundamental_service.get_comprehensive_fundamental(ticker) if request.include_fundamental else None

    tasks = [ohlcv_task, stock_info_task, current_price_task]
    if macro_task:
        tasks.append(macro_task)
    if sentiment_task:
        tasks.append(sentiment_task)
    if fundamental_task:
        tasks.append(fundamental_task)

    results = await asyncio.gather(*tasks, return_exceptions=True)

    ohlcv = results[0] if not isinstance(results[0], Exception) else None
    stock_info = results[1] if not isinstance(results[1], Exception) else {}
    price_data = results[2] if not isinstance(results[2], Exception) else None

    idx = 3
    macro_data = results[idx] if macro_task and not isinstance(results[idx], Exception) else None
    if macro_task:
        idx += 1
    sentiment_data = results[idx] if sentiment_task and not isinstance(results[idx], Exception) else None
    if sentiment_task:
        idx += 1
    fundamental_data = results[idx] if fundamental_task and not isinstance(results[idx], Exception) else None

    if not ohlcv or not price_data:
        raise HTTPException(
            status_code=404,
            detail=f"{ticker} için yeterli veri bulunamadı. Geçerli bir ticker girdiğinizden emin olun."
        )

    current_price = price_data.get("price", ohlcv[-1]["close_price"])

    # 2. Teknik analiz
    ta_result = technical_service.analyze(ohlcv, "1d") if request.include_technical else {}

    # 3. ML Tahmin Motoru (Bölüm 3'te implemente edilecek)
    # Şimdilik: kural tabanlı hızlı tahmin (placeholder)
    try:
        from app.services.ml.prediction import prediction_engine
        ml_result = await prediction_engine.predict(
            ticker=ticker,
            timeframe=timeframe,
            ohlcv=ohlcv,
            technical=ta_result,
            sentiment=sentiment_data,
            fundamental=fundamental_data,
            macro=macro_data,
        )
    except ImportError:
        # ML motoru henüz hazır değil — kural tabanlı fallback
        ml_result = _rule_based_prediction(
            current_price, ta_result, sentiment_data, timeframe
        )

    # 4. Yanıt oluştur
    from datetime import timedelta
    horizon_days = {"1d": 1, "1w": 7, "1mo": 30, "3mo": 90, "1y": 365}
    target_date = datetime.utcnow() + timedelta(days=horizon_days.get(timeframe, 1))

    response = {
        "ticker": ticker,
        "company_name": stock_info.get("company_name", ticker),
        "current_price": round(current_price, 4),
        "timeframe": timeframe,
        "prediction_date": datetime.utcnow().isoformat(),
        "target_date": target_date.isoformat(),
        "predicted_price": ml_result["predicted_price"],
        "lower_bound": ml_result.get("lower_bound"),
        "upper_bound": ml_result.get("upper_bound"),
        "predicted_return_pct": ml_result.get("predicted_return_pct"),
        "direction": ml_result["direction"],
        "direction_confidence": ml_result["direction_confidence"],
        "technical_score": ta_result.get("signals", {}).get("composite_signal"),
        "sentiment_score": sentiment_data.get("overall_score") if sentiment_data else None,
        "fundamental_score": fundamental_data.get("fundamental_score") if fundamental_data else None,
        "macro_score": _macro_to_score(macro_data) if macro_data else None,
        "risk_level": ml_result.get("risk_level", "medium"),
        "volatility_estimate": ml_result.get("volatility_estimate"),
        "anomaly_detected": ml_result.get("anomaly_detected", False),
        "model_version": ml_result.get("model_version", "rule_based_v1"),
        "ensemble_weights": ml_result.get("ensemble_weights"),
        "model_contributions": ml_result.get("model_contributions"),
        "disclaimer": DISCLAIMER,
        "technical_details": ta_result.get("indicators") if request.include_technical else None,
        "sentiment_details": sentiment_data if request.include_sentiment else None,
        "fundamental_details": {
            "pe_ratio": fundamental_data.get("pe_ratio"),
            "eps": fundamental_data.get("eps"),
            "revenue_growth_yoy": fundamental_data.get("revenue_growth_yoy"),
            "fundamental_score": fundamental_data.get("fundamental_score"),
            "insider_signal": fundamental_data.get("insider_signal"),
        } if fundamental_data and request.include_fundamental else None,
        "macro_details": {
            "fed_rate": macro_data.get("fed_rate"),
            "vix": macro_data.get("vix"),
            "yield_curve_spread": macro_data.get("yield_curve_spread"),
            "macro_regime": macro_data.get("macro_regime"),
            "macro_risk_score": macro_data.get("macro_risk_score"),
        } if macro_data and request.include_macro else None,
    }

    # Cache'e yaz
    await cache_manager.set(
        CacheNamespace.PREDICTION,
        cache_key,
        response,
        ttl=3600,
    )

    return response


@router.get("/batch")
async def batch_predict(
    tickers: str = Query(..., description="Virgülle ayrılmış ticker listesi: AAPL,TSLA,MSFT"),
    timeframe: str = Query(default="1d"),
):
    """
    Birden fazla hisse için toplu tahmin.
    Maksimum 10 ticker.
    """
    ticker_list = [t.strip().upper() for t in tickers.split(",")][:10]

    import asyncio
    tasks = [
        predict_stock(
            PredictionRequest(ticker=t, timeframe=timeframe),
            background_tasks=None,
        )
        for t in ticker_list
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    return {
        "timeframe": timeframe,
        "predictions": [
            r if not isinstance(r, Exception) else {"ticker": t, "error": str(r)}
            for t, r in zip(ticker_list, results)
        ],
        "disclaimer": DISCLAIMER,
    }


@router.get("/screener")
async def stock_screener(
    direction: Optional[str] = Query(default=None, description="up, down, sideways"),
    min_confidence: float = Query(default=0.6, ge=0, le=1),
    timeframe: str = Query(default="1d"),
    limit: int = Query(default=10, ge=1, le=50),
):
    """
    Belirtilen kriterlere uyan hisseleri listeler.
    İzleme listesindeki hisseleri tarar.
    """
    from app.tasks.data_tasks import WATCHLIST_TICKERS
    import asyncio

    tickers_to_screen = WATCHLIST_TICKERS[:20]

    tasks = [
        predict_stock(
            PredictionRequest(
                ticker=t, timeframe=timeframe,
                include_fundamental=False,  # Hız için temel analiz atla
            ),
            background_tasks=None,
        )
        for t in tickers_to_screen
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    filtered = []
    for result in results:
        if isinstance(result, Exception):
            continue
        if direction and result.get("direction") != direction:
            continue
        if result.get("direction_confidence", 0) < min_confidence:
            continue
        filtered.append(result)

    # Güven skoruna göre sırala
    filtered.sort(key=lambda x: x.get("direction_confidence", 0), reverse=True)

    return {
        "criteria": {"direction": direction, "min_confidence": min_confidence, "timeframe": timeframe},
        "results": filtered[:limit],
        "total_found": len(filtered),
        "disclaimer": DISCLAIMER,
    }


# ----------------------------------------------------------
# Yardımcı Fonksiyonlar
# ----------------------------------------------------------

def _rule_based_prediction(
    current_price: float,
    ta_result: dict,
    sentiment_data: Optional[dict],
    timeframe: str,
) -> dict:
    """
    ML motoru hazır olmadan önce çalışan kural tabanlı tahmin.
    Teknik sinyal + sentiment kombinasyonu.
    """
    import random

    composite_signal = ta_result.get("signals", {}).get("composite_signal", 0.0) or 0.0
    sentiment_score = (sentiment_data or {}).get("overall_score", 0.0) or 0.0

    # Ağırlıklı sinyal
    combined = composite_signal * 0.6 + sentiment_score * 0.4

    # Zaman dilimine göre volatilite varsayımı
    vol_map = {"1d": 0.015, "1w": 0.035, "1mo": 0.08, "3mo": 0.15, "1y": 0.30}
    vol = vol_map.get(timeframe, 0.02)

    predicted_return = combined * vol * 3
    predicted_price = round(current_price * (1 + predicted_return), 4)

    direction = "up" if combined > 0.1 else ("down" if combined < -0.1 else "sideways")
    confidence = min(0.95, 0.5 + abs(combined) * 0.5)

    return {
        "predicted_price": predicted_price,
        "lower_bound": round(predicted_price * (1 - vol * 1.5), 4),
        "upper_bound": round(predicted_price * (1 + vol * 1.5), 4),
        "predicted_return_pct": round(predicted_return * 100, 2),
        "direction": direction,
        "direction_confidence": round(confidence, 4),
        "risk_level": "high" if vol > 0.10 else "medium" if vol > 0.04 else "low",
        "volatility_estimate": round(vol, 4),
        "anomaly_detected": False,
        "model_version": "rule_based_v1",
        "ensemble_weights": None,
        "model_contributions": None,
    }


def _macro_to_score(macro_data: dict) -> float:
    """Makro risk skorunu -1 ile 1 arası sinyale çevirir."""
    risk = macro_data.get("macro_risk_score", 50)
    # 0-100 → -1 (yüksek risk=negatif) ile 1 (düşük risk=pozitif)
    return round((50 - risk) / 50, 4)

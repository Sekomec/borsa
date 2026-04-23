"""
QuantEdge AI — Celery ML Tahmin Görevleri
==========================================
Arka plan model eğitimi ve tahmin önbellekleme.
"""

import asyncio
from datetime import datetime
from typing import List, Optional

import structlog

from app.tasks.celery_app import celery_app
from app.tasks.data_tasks import WATCHLIST_TICKERS, run_async

logger = structlog.get_logger()


@celery_app.task(
    name="app.tasks.prediction_tasks.retrain_all_models",
    bind=True,
    queue="ml_prediction",
    time_limit=14400,   # 4 saat — tüm modeller için
    soft_time_limit=13000,
)
def retrain_all_models(self, tickers: Optional[List[str]] = None):
    """
    Haftalık model yeniden eğitimi.
    Her Pazar 03:00 ET'de otomatik çalışır.
    """
    from app.services.ml.training import model_trainer

    target_tickers = tickers or WATCHLIST_TICKERS[:10]  # İlk 10 ticker
    timeframes = ["1d", "1w", "1mo"]

    logger.info(
        "Haftalık model yeniden eğitimi başlıyor.",
        tickers=len(target_tickers),
        timeframes=timeframes,
    )

    results = {"trained": 0, "failed": 0, "details": {}}

    async def _retrain():
        from app.services.data_fetchers.market_data import market_data_service
        from app.services.data_fetchers.sentiment import sentiment_service
        from app.services.data_fetchers.fundamental import fundamental_service
        from app.services.data_fetchers.macro import macro_service
        from app.services.analysis.technical import technical_service

        for ticker in target_tickers:
            results["details"][ticker] = {}

            try:
                # Veriyi çek
                ohlcv = await market_data_service.get_ohlcv(ticker, "1d", 500, use_cache=False)
                if not ohlcv or len(ohlcv) < 100:
                    logger.warning("Yetersiz veri.", ticker=ticker, bars=len(ohlcv) if ohlcv else 0)
                    results["failed"] += 1
                    continue

                ta = technical_service.analyze(ohlcv, "1d")
                sentiment = await sentiment_service.get_aggregated_sentiment(ticker)
                fundamental = await fundamental_service.get_comprehensive_fundamental(ticker)
                macro = await macro_service.get_full_macro_context()

                for tf in timeframes:
                    try:
                        train_result = model_trainer.train_all_models(
                            ticker=ticker,
                            timeframe=tf,
                            ohlcv=ohlcv,
                            technical=ta,
                            sentiment=sentiment,
                            fundamental=fundamental,
                            macro=macro,
                            optimize_hyperparams=(tf == "1d"),  # Yalnızca günlük için Optuna
                        )
                        results["details"][ticker][tf] = train_result.get("status")
                        if train_result.get("status") == "success":
                            results["trained"] += 1
                        else:
                            results["failed"] += 1
                    except Exception as e:
                        results["failed"] += 1
                        results["details"][ticker][tf] = f"error: {str(e)[:50]}"

                # API rate limit koruması
                await asyncio.sleep(5)

            except Exception as e:
                results["failed"] += 1
                logger.error("Ticker eğitim hatası.", ticker=ticker, error=str(e))

    try:
        run_async(_retrain())
        logger.info("Haftalık eğitim tamamlandı.", **{k: v for k, v in results.items() if k != "details"})
        return {"status": "ok", **results}
    except Exception as exc:
        logger.error("Haftalık eğitim genel hatası.", error=str(exc))
        return {"status": "error", "error": str(exc)}


@celery_app.task(
    name="app.tasks.prediction_tasks.precompute_predictions",
    bind=True,
    queue="ml_prediction",
    time_limit=3600,
)
def precompute_predictions(
    self,
    tickers: str = "WATCHLIST",
    timeframes: Optional[List[str]] = None,
):
    """
    Popüler hisseler için tahminleri önceden hesaplar ve cache'ler.
    Her gün 17:00 ET'de çalışır — kullanıcı isteklerinde hızlı yanıt.
    """
    from app.core.cache import cache_manager, CacheNamespace

    target_tickers = WATCHLIST_TICKERS[:20] if tickers == "WATCHLIST" else tickers.split(",")
    target_timeframes = timeframes or ["1d", "1w"]

    logger.info(
        "Tahmin önbellekleme başlıyor.",
        tickers=len(target_tickers),
        timeframes=target_timeframes,
    )

    async def _precompute():
        from app.services.data_fetchers.market_data import market_data_service
        from app.services.data_fetchers.sentiment import sentiment_service
        from app.services.data_fetchers.macro import macro_service
        from app.services.data_fetchers.fundamental import fundamental_service
        from app.services.analysis.technical import technical_service
        from app.services.ml.prediction import prediction_engine

        cached_count = 0

        for ticker in target_tickers:
            try:
                ohlcv = await market_data_service.get_ohlcv(ticker, "1d", 365)
                if not ohlcv:
                    continue

                ta = technical_service.analyze(ohlcv)
                sentiment, fundamental, macro = await asyncio.gather(
                    sentiment_service.get_aggregated_sentiment(ticker),
                    fundamental_service.get_comprehensive_fundamental(ticker),
                    macro_service.get_full_macro_context(),
                    return_exceptions=True,
                )

                for tf in target_timeframes:
                    cache_key = f"{ticker}:{tf}:prediction"
                    # Zaten cache'de varsa atla
                    existing = await cache_manager.get(CacheNamespace.PREDICTION, cache_key)
                    if existing:
                        continue

                    result = await prediction_engine.predict(
                        ticker=ticker, timeframe=tf,
                        ohlcv=ohlcv, technical=ta,
                        sentiment=sentiment if not isinstance(sentiment, Exception) else None,
                        fundamental=fundamental if not isinstance(fundamental, Exception) else None,
                        macro=macro if not isinstance(macro, Exception) else None,
                    )

                    await cache_manager.set(
                        CacheNamespace.PREDICTION, cache_key,
                        result, ttl=3600 * 4,
                    )
                    cached_count += 1

                await asyncio.sleep(2)

            except Exception as e:
                logger.warning("Ön hesaplama hatası.", ticker=ticker, error=str(e))

        return cached_count

    try:
        count = run_async(_precompute())
        logger.info("Tahmin önbellekleme tamamlandı.", cached=count)
        return {"status": "ok", "cached_predictions": count}
    except Exception as exc:
        logger.error("Önbellekleme başarısız.", error=str(exc))
        return {"status": "error", "error": str(exc)}


@celery_app.task(
    name="app.tasks.prediction_tasks.train_single_model",
    bind=True,
    queue="ml_prediction",
    time_limit=1800,  # 30 dakika
)
def train_single_model(
    self,
    ticker: str,
    timeframe: str = "1d",
    optimize: bool = False,
):
    """
    Tek bir hisse için modeli eğitir.
    Kullanıcı "yeni hisse ekle" istediğinde tetiklenir.
    """
    from app.services.ml.training import model_trainer

    async def _train():
        from app.services.data_fetchers.market_data import market_data_service
        from app.services.data_fetchers.sentiment import sentiment_service
        from app.services.data_fetchers.fundamental import fundamental_service
        from app.services.data_fetchers.macro import macro_service
        from app.services.analysis.technical import technical_service

        ohlcv = await market_data_service.get_ohlcv(ticker, "1d", 500, use_cache=False)
        if not ohlcv or len(ohlcv) < 100:
            raise ValueError(f"{ticker} için yetersiz veri ({len(ohlcv or [])} bar).")

        ta = technical_service.analyze(ohlcv)
        sentiment = await sentiment_service.get_aggregated_sentiment(ticker)
        fundamental = await fundamental_service.get_comprehensive_fundamental(ticker)
        macro = await macro_service.get_full_macro_context()

        return model_trainer.train_all_models(
            ticker=ticker, timeframe=timeframe,
            ohlcv=ohlcv, technical=ta,
            sentiment=sentiment, fundamental=fundamental, macro=macro,
            optimize_hyperparams=optimize,
        )

    try:
        result = run_async(_train())
        logger.info("Tek model eğitimi tamamlandı.", ticker=ticker, timeframe=timeframe)
        return result
    except Exception as exc:
        logger.error("Tek model eğitimi başarısız.", ticker=ticker, error=str(exc))
        raise self.retry(exc=exc, max_retries=1)

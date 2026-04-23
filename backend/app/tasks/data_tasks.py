"""
QuantEdge AI — Celery Veri Çekme Görevleri
============================================
Periyodik veri güncelleme ve arka plan işlemleri.

Görev Planlaması:
  - Piyasa açıkken (09:30-16:00 ET): Her dakika fiyat güncelleme
  - Her 30 dakika: Sentiment güncelleme
  - Günlük 16:30: Tam veri tazeleme
  - Haftalık Pazar: Model yeniden eğitimi
"""

import asyncio
from datetime import datetime
from typing import List, Optional

import structlog
from celery import shared_task

from app.tasks.celery_app import celery_app

logger = structlog.get_logger()

# S&P 500 ve NASDAQ-100'den seçilmiş izleme listesi
WATCHLIST_TICKERS = [
    # NASDAQ Mega-Cap
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
    # NYSE Blue Chip
    "JPM", "JNJ", "V", "WMT", "UNH", "XOM", "PG",
    # Yüksek Volatilite / WSB Favorileri
    "AMD", "PLTR", "GME", "AMC", "RIVN", "LCID",
    # ETF
    "SPY", "QQQ", "IWM", "DIA",
]


def run_async(coro):
    """Celery task içinde async kod çalıştırmak için yardımcı."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)


# ----------------------------------------------------------
# GERÇEK ZAMANLI PİYASA VERİSİ
# ----------------------------------------------------------

@celery_app.task(
    name="app.tasks.data_tasks.fetch_realtime_market_data",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue="data_fetch",
)
def fetch_realtime_market_data(self, tickers: str = "WATCHLIST"):
    """
    Piyasa açıkken her dakika çalışır.
    Anlık fiyatları çekerek Redis cache'i günceller.
    """
    from app.services.data_fetchers.market_data import market_data_service
    from app.core.cache import cache_manager, CacheNamespace

    ticker_list = WATCHLIST_TICKERS if tickers == "WATCHLIST" else tickers.split(",")

    logger.info("Gerçek zamanlı veri güncelleniyor.", ticker_count=len(ticker_list))

    async def _fetch_all():
        tasks = [market_data_service.get_current_price(t) for t in ticker_list]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        success = sum(1 for r in results if not isinstance(r, Exception) and r is not None)
        return success

    try:
        success_count = run_async(_fetch_all())
        logger.info("Gerçek zamanlı güncelleme tamamlandı.", success=success_count, total=len(ticker_list))
        return {"status": "ok", "updated": success_count, "total": len(ticker_list)}
    except Exception as exc:
        logger.error("Gerçek zamanlı güncelleme başarısız.", error=str(exc))
        raise self.retry(exc=exc)


# ----------------------------------------------------------
# SENTİMENT GÜNCELLEME
# ----------------------------------------------------------

@celery_app.task(
    name="app.tasks.data_tasks.update_sentiment_scores",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    queue="data_fetch",
    time_limit=600,   # 10 dakika timeout
)
def update_sentiment_scores(self, tickers: str = "WATCHLIST"):
    """
    Her 30 dakikada çalışır.
    Reddit, StockTwits ve haber kaynaklarından sentiment günceller.
    """
    from app.services.data_fetchers.sentiment import sentiment_service

    ticker_list = WATCHLIST_TICKERS[:20] if tickers == "WATCHLIST" else tickers.split(",")

    logger.info("Sentiment güncelleniyor.", ticker_count=len(ticker_list))

    async def _update_sentiment():
        results = {}
        # Rate limit aşmamak için sıralı işle (paralel değil)
        for ticker in ticker_list:
            try:
                sentiment = await sentiment_service.get_aggregated_sentiment(ticker)
                results[ticker] = sentiment.get("overall_score", 0)
            except Exception as e:
                logger.warning("Sentiment güncellenemedi.", ticker=ticker, error=str(e))
                results[ticker] = None
            # API rate limit koruması
            await asyncio.sleep(1)
        return results

    try:
        results = run_async(_update_sentiment())
        logger.info("Sentiment güncelleme tamamlandı.", tickers_updated=len(results))
        return {"status": "ok", "results": results}
    except Exception as exc:
        logger.error("Sentiment güncelleme başarısız.", error=str(exc))
        raise self.retry(exc=exc)


# ----------------------------------------------------------
# GÜNLÜK TAM VERİ YENİLEME
# ----------------------------------------------------------

@celery_app.task(
    name="app.tasks.data_tasks.daily_data_refresh",
    bind=True,
    queue="data_fetch",
    time_limit=3600,   # 1 saat timeout
)
def daily_data_refresh(self):
    """
    Her gün piyasa kapandıktan sonra (16:30 ET) çalışır.
    Günlük OHLCV verilerini tüm ticker'lar için günceller.
    """
    from app.services.data_fetchers.market_data import market_data_service
    from app.services.analysis.technical import technical_service

    logger.info("Günlük veri tazeleme başladı.", date=datetime.utcnow().date().isoformat())

    async def _refresh():
        results = {"ohlcv_updated": 0, "technical_computed": 0, "errors": []}

        for ticker in WATCHLIST_TICKERS:
            try:
                # OHLCV güncelle (cache bypass)
                ohlcv = await market_data_service.get_ohlcv(
                    ticker, timeframe="1d", limit=365, use_cache=False
                )
                if ohlcv:
                    results["ohlcv_updated"] += 1

                    # Teknik analiz hesapla
                    ta_result = technical_service.analyze(ohlcv, timeframe="1d")
                    results["technical_computed"] += 1

                await asyncio.sleep(0.5)   # Rate limit

            except Exception as e:
                results["errors"].append({"ticker": ticker, "error": str(e)})
                logger.warning("Günlük güncelleme hatası.", ticker=ticker, error=str(e))

        return results

    try:
        result = run_async(_refresh())
        logger.info("Günlük veri tazeleme tamamlandı.", **result)
        return {"status": "ok", **result}
    except Exception as exc:
        logger.error("Günlük veri tazeleme başarısız.", error=str(exc))
        return {"status": "error", "error": str(exc)}


# ----------------------------------------------------------
# TEMEL ANALİZ GÜNCELLEMESİ
# ----------------------------------------------------------

@celery_app.task(
    name="app.tasks.data_tasks.update_fundamental_data",
    bind=True,
    queue="data_fetch",
    time_limit=7200,  # 2 saat
)
def update_fundamental_data(self):
    """
    Haftalık temel analiz verilerini günceller.
    Finnhub + SEC EDGAR kaynaklarından.
    """
    from app.services.data_fetchers.fundamental import fundamental_service

    logger.info("Temel analiz verisi güncelleniyor.")

    async def _update_fundamentals():
        results = {"updated": 0, "errors": []}
        # Temel analiz daha seyrek güncellenir — sadece büyük ticker'lar
        priority_tickers = WATCHLIST_TICKERS[:15]

        for ticker in priority_tickers:
            try:
                await fundamental_service.get_comprehensive_fundamental(ticker)
                results["updated"] += 1
                await asyncio.sleep(2)  # Finnhub rate limit koruması
            except Exception as e:
                results["errors"].append({"ticker": ticker, "error": str(e)})

        return results

    try:
        result = run_async(_update_fundamentals())
        logger.info("Temel analiz güncelleme tamamlandı.", **result)
        return {"status": "ok", **result}
    except Exception as exc:
        logger.error("Temel analiz güncelleme başarısız.", error=str(exc))
        return {"status": "error", "error": str(exc)}


# ----------------------------------------------------------
# MAKRO GÖSTERGE GÜNCELLEMESİ
# ----------------------------------------------------------

@celery_app.task(
    name="app.tasks.data_tasks.update_macro_indicators",
    bind=True,
    queue="data_fetch",
    time_limit=300,
)
def update_macro_indicators(self):
    """
    Günlük FRED API'den makroekonomik göstergeleri günceller.
    Piyasa açılmadan önce (08:00 ET) çalışır.
    """
    from app.services.data_fetchers.macro import macro_service

    logger.info("Makro göstergeler güncelleniyor.")

    async def _update_macro():
        # Cache bypass ile taze veri çek
        context = await macro_service.get_full_macro_context()
        return {
            "fed_rate": context.get("fed_rate"),
            "vix": context.get("vix"),
            "yield_curve": context.get("yield_curve_spread"),
            "macro_regime": context.get("macro_regime"),
        }

    try:
        result = run_async(_update_macro())
        logger.info("Makro güncelleme tamamlandı.", **result)
        return {"status": "ok", **result}
    except Exception as exc:
        logger.error("Makro güncelleme başarısız.", error=str(exc))
        raise self.retry(exc=exc)


# ----------------------------------------------------------
# TEK TICKER VERİ HAZIRLIĞI (On-Demand)
# ----------------------------------------------------------

@celery_app.task(
    name="app.tasks.data_tasks.prepare_ticker_data",
    bind=True,
    queue="data_fetch",
    time_limit=120,
)
def prepare_ticker_data(self, ticker: str, timeframes: Optional[List[str]] = None):
    """
    Tek bir ticker için tüm modüllerin verisini hazırlar.
    Tahmin isteği geldiğinde on-demand çalışır.
    """
    from app.services.data_fetchers.market_data import market_data_service
    from app.services.data_fetchers.fundamental import fundamental_service
    from app.services.data_fetchers.sentiment import sentiment_service
    from app.services.data_fetchers.macro import macro_service

    if timeframes is None:
        timeframes = ["1d", "1w"]

    logger.info("Ticker verisi hazırlanıyor.", ticker=ticker, timeframes=timeframes)

    async def _prepare():
        tasks = [
            market_data_service.get_ohlcv(ticker, "1d", 365),
            fundamental_service.get_comprehensive_fundamental(ticker),
            sentiment_service.get_aggregated_sentiment(ticker),
            macro_service.get_full_macro_context(),
            market_data_service.get_stock_info(ticker),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return {
            "ohlcv": not isinstance(results[0], Exception) and results[0] is not None,
            "fundamental": not isinstance(results[1], Exception),
            "sentiment": not isinstance(results[2], Exception),
            "macro": not isinstance(results[3], Exception),
            "stock_info": not isinstance(results[4], Exception),
        }

    try:
        readiness = run_async(_prepare())
        logger.info("Ticker verisi hazır.", ticker=ticker, **readiness)
        return {"status": "ready", "ticker": ticker, "modules": readiness}
    except Exception as exc:
        logger.error("Ticker veri hazırlama başarısız.", ticker=ticker, error=str(exc))
        raise self.retry(exc=exc)

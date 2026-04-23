"""
QuantEdge AI — Piyasa Verisi Çekme Modülü
===========================================
Birincil kaynak: Polygon.io
Yedek zinciri : Alpha Vantage → Finnhub → yfinance (mock'a kadar)

Tüm fonksiyonlar:
- Async HTTP
- Rate limiter korumalı
- Exponential backoff retry
- Fallback zinciri
- Cache entegrasyonu
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import aiohttp
import structlog
import yfinance as yf
import pandas as pd

from app.core.config import settings
from app.core.cache import cache_manager, CacheNamespace
from app.utils.retry import async_retry, polygon_limiter, alpha_vantage_limiter, finnhub_limiter

logger = structlog.get_logger()


def _iso8601_utc(dt: datetime) -> str:
    """
    JSON/JS tarafında problemsiz parse edilebilmesi için ISO-8601 UTC string üret.
    (Cache katmanı json.dumps(default=str) yaptığı için datetime -> 'YYYY-MM-DD HH:MM:SS' olabiliyor.)
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=None).isoformat() + "Z"
    return dt.astimezone(tz=None).isoformat()


def _normalize_bars(bars: List[Dict]) -> List[Dict]:
    """Timestamp alanını ISO-8601 string'e çevirir (chart uyumluluğu için)."""
    normalized: List[Dict] = []
    for b in bars:
        bb = dict(b)
        ts = bb.get("timestamp")
        if isinstance(ts, datetime):
            bb["timestamp"] = _iso8601_utc(ts)
        normalized.append(bb)
    return normalized


# ----------------------------------------------------------
# POLYGON.IO FETCHER (Birincil Kaynak)
# ----------------------------------------------------------

class PolygonFetcher:
    """
    Polygon.io REST API istemcisi.
    Gerçek zamanlı ve tarihsel OHLCV, tick verisi sağlar.

    Ücretsiz plan: Dakikada 5 istek, 2 yıllık geçmiş
    Ücretli plan : Sınırsız istek, tam tarihsel veri
    """

    BASE_URL = "https://api.polygon.io/v2"
    BASE_URL_V3 = "https://api.polygon.io/v3"

    def __init__(self):
        self.api_key = settings.POLYGON_API_KEY
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=15)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        return self._session

    @async_retry(max_attempts=3, delay=2.0, backoff=2.0)
    async def get_ohlcv(
        self,
        ticker: str,
        timeframe: str = "1d",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 365,
    ) -> Optional[List[Dict]]:
        """
        OHLCV bar verisi çeker.

        Args:
            ticker    : Hisse kodu (AAPL, TSLA...)
            timeframe : '1d', '1h', '5m'
            start_date: 'YYYY-MM-DD'
            end_date  : 'YYYY-MM-DD'
            limit     : Maksimum bar sayısı

        Returns:
            [{'timestamp': ..., 'open': ..., 'high': ..., 'low': ..., 'close': ..., 'volume': ...}]
        """
        if not self.api_key:
            raise ValueError("POLYGON_API_KEY tanımlı değil.")

        # Zaman dilimi mapping: uygulama formatı → Polygon formatı
        tf_map = {"1d": "day", "1h": "hour", "5m": "minute", "1w": "week"}
        multiplier_map = {"1d": 1, "1h": 1, "5m": 5, "1w": 1}

        span = tf_map.get(timeframe, "day")
        multiplier = multiplier_map.get(timeframe, 1)

        end = end_date or datetime.utcnow().strftime("%Y-%m-%d")
        start = start_date or (datetime.utcnow() - timedelta(days=limit)).strftime("%Y-%m-%d")

        url = f"{self.BASE_URL}/aggs/ticker/{ticker}/range/{multiplier}/{span}/{start}/{end}"
        params = {"adjusted": "true", "sort": "asc", "limit": limit}

        async with polygon_limiter():
            session = await self._get_session()
            async with session.get(url, params=params) as resp:
                if resp.status == 429:
                    raise Exception("Polygon rate limit aşıldı.")
                if resp.status == 403:
                    raise ValueError("Geçersiz Polygon API anahtarı.")
                if resp.status != 200:
                    raise Exception(f"Polygon API hatası: {resp.status}")

                data = await resp.json()

        if data.get("status") == "ERROR":
            raise Exception(f"Polygon API error: {data.get('error')}")

        results = data.get("results", [])
        if not results:
            logger.warning("Polygon'dan boş veri döndü.", ticker=ticker, timeframe=timeframe)
            return None

        return [
            {
                "timestamp": datetime.utcfromtimestamp(bar["t"] / 1000),
                "open_price": bar["o"],
                "high_price": bar["h"],
                "low_price": bar["l"],
                "close_price": bar["c"],
                "volume": bar["v"],
                "vwap": bar.get("vw"),
            }
            for bar in results
        ]

    @async_retry(max_attempts=3, delay=1.0)
    async def get_last_quote(self, ticker: str) -> Optional[Dict]:
        """Anlık fiyat teklifi çeker."""
        if not self.api_key:
            raise ValueError("POLYGON_API_KEY tanımlı değil.")

        # Not: Bazı hesaplarda /v3/trades yetkisi 403 dönebilir.
        # Daha geniş erişime sahip, tek fiyat veren v2 last trade endpoint'i kullanıyoruz.
        url = f"{self.BASE_URL}/last/trade/{ticker}"
        params = {"apiKey": self.api_key}

        async with polygon_limiter():
            session = await self._get_session()
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    raise Exception(f"Polygon quote hatası: {resp.status}")
                data = await resp.json()

        results = data.get("results") or {}
        price = results.get("p")
        if price is None:
            return None

        return {
            "ticker": ticker,
            "price": float(price),
            "size": results.get("s"),
            "timestamp": results.get("t"),
            "source": "polygon",
        }

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


# ----------------------------------------------------------
# ALPHA VANTAGE FETCHER (İkincil Kaynak)
# ----------------------------------------------------------

class AlphaVantageFetcher:
    """
    Alpha Vantage API istemcisi.
    OHLCV, teknik göstergeler ve temel analiz verileri sağlar.

    Ücretsiz plan: Dakikada 5 istek, 500 istek/gün
    """

    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self):
        self.api_key = settings.ALPHA_VANTAGE_API_KEY

    @async_retry(max_attempts=3, delay=15.0, backoff=2.0)  # AV yavaş, uzun bekle
    async def get_ohlcv(
        self,
        ticker: str,
        timeframe: str = "1d",
        limit: int = 365,
    ) -> Optional[List[Dict]]:
        """Alpha Vantage'dan OHLCV verisi çeker."""
        if not self.api_key:
            raise ValueError("ALPHA_VANTAGE_API_KEY tanımlı değil.")

        function_map = {
            "1d": "TIME_SERIES_DAILY_ADJUSTED",
            "1w": "TIME_SERIES_WEEKLY_ADJUSTED",
            "1mo": "TIME_SERIES_MONTHLY_ADJUSTED",
        }

        function = function_map.get(timeframe, "TIME_SERIES_DAILY_ADJUSTED")
        params = {
            "function": function,
            "symbol": ticker,
            "outputsize": "full" if limit > 100 else "compact",
            "apikey": self.api_key,
            "datatype": "json",
        }

        async with alpha_vantage_limiter():
            async with aiohttp.ClientSession() as session:
                async with session.get(self.BASE_URL, params=params, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status != 200:
                        raise Exception(f"Alpha Vantage HTTP hatası: {resp.status}")
                    data = await resp.json()

        # AV rate limit kontrolü
        if "Note" in data:
            raise Exception("Alpha Vantage rate limit aşıldı.")
        if "Error Message" in data:
            raise Exception(f"Alpha Vantage hatası: {data['Error Message']}")

        # Zaman serisi anahtarı bul
        ts_key = next((k for k in data if "Time Series" in k), None)
        if not ts_key:
            logger.warning("Alpha Vantage'dan boş veri.", ticker=ticker)
            return None

        ts = data[ts_key]
        results = []
        for date_str, values in list(ts.items())[:limit]:
            try:
                results.append({
                    "timestamp": datetime.strptime(date_str, "%Y-%m-%d"),
                    "open_price": float(values.get("1. open", values.get("1a. open (USD)", 0))),
                    "high_price": float(values.get("2. high", values.get("2a. high (USD)", 0))),
                    "low_price": float(values.get("3. low", values.get("3a. low (USD)", 0))),
                    "close_price": float(values.get("4. close", values.get("4a. close (USD)", 0))),
                    "volume": int(values.get("6. volume", values.get("5. volume", 0))),
                    "adjusted_close": float(values.get("5. adjusted close", 0)),
                    "vwap": None,
                })
            except (ValueError, KeyError):
                continue

        return sorted(results, key=lambda x: x["timestamp"])


# ----------------------------------------------------------
# YFINANCE FETCHER (Son Çare / Ücretsiz Fallback)
# ----------------------------------------------------------

class YFinanceFetcher:
    """
    yfinance kütüphanesi tabanlı fetcher.
    API anahtarı gerektirmez. Ücretsiz fallback kaynağı.

    Not: Ticari kullanım için Yahoo Finance ToS kontrol edilmelidir.
    """

    @async_retry(max_attempts=2, delay=3.0)
    async def get_ohlcv(
        self,
        ticker: str,
        timeframe: str = "1d",
        limit: int = 365,
    ) -> Optional[List[Dict]]:
        """yfinance ile OHLCV verisi çeker (sync → async wrapper)."""

        period_map = {
            "1d": ("1d", f"{limit}d"),
            "1h": ("1h", "60d"),   # yfinance 1h için max 60 gün
            "5m": ("5m", "5d"),
            "1w": ("1wk", "2y"),
            "1mo": ("1mo", "10y"),
        }

        interval, period = period_map.get(timeframe, ("1d", "1y"))

        # yfinance sync çağrısı → asyncio executor ile async hale getir
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(
            None,
            lambda: yf.download(ticker, period=period, interval=interval, progress=False)
        )

        if df is None or df.empty:
            logger.warning("yfinance'dan boş veri.", ticker=ticker)
            return None

        df = df.tail(limit)
        results = []
        for ts, row in df.iterrows():
            try:
                results.append({
                    "timestamp": ts.to_pydatetime() if hasattr(ts, 'to_pydatetime') else ts,
                    "open_price": float(row.get("Open", 0)),
                    "high_price": float(row.get("High", 0)),
                    "low_price": float(row.get("Low", 0)),
                    "close_price": float(row.get("Close", 0)),
                    "volume": int(row.get("Volume", 0)),
                    "adjusted_close": float(row.get("Adj Close", row.get("Close", 0))),
                    "vwap": None,
                })
            except (ValueError, KeyError):
                continue

        return results

    async def get_stock_info(self, ticker: str) -> Optional[Dict]:
        """Hisse meta verisi çeker."""
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(
            None,
            lambda: yf.Ticker(ticker).info
        )
        if not info:
            return None

        return {
            "ticker": ticker,
            "company_name": info.get("longName", ticker),
            "exchange": info.get("exchange", ""),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "market_cap": info.get("marketCap"),
            "currency": info.get("currency", "USD"),
            "country": info.get("country", "USA"),
            "source": "yfinance",
        }


# ----------------------------------------------------------
# MOCK/FALLBACK FETCHER (Development + Test)
# ----------------------------------------------------------

class MockMarketDataFetcher:
    """
    Gerçek API bağlantısı olmadan çalışmak için deterministik mock veri üreteci.
    Development ve test ortamları için kullanılır.
    """

    def __init__(self):
        import numpy as np
        self.np = np

    async def get_ohlcv(
        self,
        ticker: str,
        timeframe: str = "1d",
        limit: int = 365,
    ) -> List[Dict]:
        """Gerçekçi OHLCV mock verisi üretir."""
        np = self.np

        # Seed: ticker'a göre deterministik
        seed = sum(ord(c) for c in ticker)
        rng = np.random.default_rng(seed)

        # Başlangıç fiyatı (ticker'a göre farklı)
        # Not: Mock veri "gerçek veri" değildir; sadece UI geliştirme içindir.
        # Bazı popüler ticker'lar için daha güncel değerlere yakın tutulur.
        base_prices = {"AAPL": 190, "TSLA": 250, "MSFT": 420, "GOOGL": 340, "AMZN": 185}
        start_price = base_prices.get(ticker, 100 + seed % 200)

        prices = [start_price]
        for _ in range(limit - 1):
            drift = 0.0002   # Hafif yukarı trend
            vol = 0.015      # %1.5 günlük volatilite
            change = rng.normal(drift, vol)
            prices.append(max(prices[-1] * (1 + change), 1.0))

        end_date = datetime.utcnow()
        results = []
        for i, close in enumerate(prices):
            dt = end_date - timedelta(days=limit - i - 1)
            high = close * (1 + abs(rng.normal(0, 0.008)))
            low = close * (1 - abs(rng.normal(0, 0.008)))
            open_p = prices[i - 1] if i > 0 else close * (1 + rng.normal(0, 0.005))

            results.append({
                "timestamp": dt.replace(hour=0, minute=0, second=0, microsecond=0),
                "open_price": round(open_p, 4),
                "high_price": round(high, 4),
                "low_price": round(low, 4),
                "close_price": round(close, 4),
                "volume": int(rng.integers(1_000_000, 50_000_000)),
                "vwap": round((high + low + close) / 3, 4),
                "adjusted_close": round(close, 4),
            })

        return results


# ----------------------------------------------------------
# ANA MARKET DATA SERVİSİ — Fallback Zinciri
# ----------------------------------------------------------

class MarketDataService:
    """
    Tüm market data fetcher'larını yöneten ana servis.

    Fallback Zinciri:
    Polygon.io → Alpha Vantage → yfinance → Mock (dev)

    Her aşamada:
    1. Cache kontrolü (Redis)
    2. API çağrısı (rate limiter + retry)
    3. Hata durumunda bir sonraki kaynağa geç
    4. Sonucu cache'e yaz
    """

    def __init__(self):
        self.polygon = PolygonFetcher()
        self.alpha_vantage = AlphaVantageFetcher()
        self.yfinance = YFinanceFetcher()
        self.mock = MockMarketDataFetcher()

    async def get_ohlcv(
        self,
        ticker: str,
        timeframe: str = "1d",
        limit: int = 365,
        use_cache: bool = True,
    ) -> Optional[List[Dict]]:
        """
        Fallback zinciri ile OHLCV verisi çeker.

        Args:
            ticker    : Hisse kodu
            timeframe : Zaman dilimi
            limit     : Bar sayısı
            use_cache : Cache kullanılsın mı?

        Returns:
            OHLCV bar listesi veya None
        """
        cache_key = f"{ticker}:{timeframe}:{limit}"

        # Cache kontrolü
        if use_cache:
            cached = await cache_manager.get(CacheNamespace.OHLCV, cache_key)
            if cached:
                logger.debug("OHLCV cache hit.", ticker=ticker, timeframe=timeframe)
                return cached

        # Fallback zinciri
        fetchers = self._build_fetcher_chain()
        last_error = None

        for name, fetcher in fetchers:
            try:
                logger.info(f"OHLCV çekiliyor.", source=name, ticker=ticker, timeframe=timeframe)
                # Not: Fetcher imzaları farklı (Polygon: start_date/end_date opsiyonel).
                # Bu yüzden limit'i pozisyonel göndermek Polygon'da start_date'e kayabilir.
                data = await fetcher.get_ohlcv(ticker, timeframe=timeframe, limit=limit)

                if data:
                    data = _normalize_bars(data)
                    # Cache'e yaz
                    ttl = self._get_cache_ttl(timeframe)
                    await cache_manager.set(CacheNamespace.OHLCV, cache_key, data, ttl)
                    logger.info("OHLCV başarıyla çekildi.", source=name, ticker=ticker, bars=len(data))
                    return data

            except Exception as e:
                last_error = e
                logger.warning(
                    f"OHLCV çekme başarısız, sonraki kaynağa geçiliyor.",
                    source=name, ticker=ticker, error=str(e)
                )
                continue

        # Tüm kaynaklar başarısız → mock data (development)
        if settings.is_development:
            logger.warning("Tüm API kaynakları başarısız. Mock veri kullanılıyor.", ticker=ticker)
            mock_data = await self.mock.get_ohlcv(ticker, timeframe, limit)
            return _normalize_bars(mock_data)

        logger.error("OHLCV çekilemedi.", ticker=ticker, last_error=str(last_error))
        return None

    async def get_current_price(self, ticker: str) -> Optional[Dict]:
        """Anlık fiyat bilgisi çeker."""
        cache_key = f"{ticker}:current"
        cached = await cache_manager.get(CacheNamespace.MARKET_DATA, cache_key)
        if cached:
            return cached

        # Polygon en güncel fiyatı sağlar
        if settings.has_polygon:
            try:
                quote = await self.polygon.get_last_quote(ticker)
                if quote:
                    await cache_manager.set(CacheNamespace.MARKET_DATA, cache_key, quote, ttl=30)
                    return quote
            except Exception as e:
                logger.warning("Anlık fiyat Polygon'dan alınamadı.", ticker=ticker, error=str(e))

            # Bazı Polygon planlarında "last trade/quote" endpoint'leri 403 dönebilir.
            # Bu durumda aynı API anahtarıyla erişilebilen OHLCV (adjusted) son kapanışını kullan.
            try:
                bars = await self.polygon.get_ohlcv(ticker, timeframe="1d", limit=2)
                if bars:
                    last = bars[-1]
                    result = {
                        "ticker": ticker,
                        "price": float(last.get("close_price")),
                        "timestamp": last.get("timestamp"),
                        "source": "polygon_ohlcv",
                    }
                    await cache_manager.set(CacheNamespace.MARKET_DATA, cache_key, result, ttl=60)
                    return result
            except Exception as e:
                logger.warning("Anlık fiyat Polygon OHLCV'den alınamadı.", ticker=ticker, error=str(e))

        # yfinance fallback
        try:
            loop = asyncio.get_event_loop()
            ticker_obj = yf.Ticker(ticker)
            # fast_info genelde en güvenilir/ hızlı quote kaynağı
            fast_info = await loop.run_in_executor(None, lambda: getattr(ticker_obj, "fast_info", None))
            price = None
            if isinstance(fast_info, dict):
                price = fast_info.get("last_price") or fast_info.get("regular_market_price")

            if price is None:
                hist = await loop.run_in_executor(None, lambda: ticker_obj.history(period="1d"))
                if not hist.empty:
                    price = float(hist["Close"].iloc[-1])

            if price is not None:
                result = {"ticker": ticker, "price": float(price), "source": "yfinance"}
                await cache_manager.set(CacheNamespace.MARKET_DATA, cache_key, result, ttl=60)
                return result
        except Exception as e:
            logger.warning("Anlık fiyat yfinance'dan alınamadı.", ticker=ticker, error=str(e))

        # Mock (development)
        if settings.is_development:
            mock = await self.mock.get_ohlcv(ticker, "1d", 1)
            if mock:
                return {"ticker": ticker, "price": mock[-1]["close_price"], "source": "mock"}

        return None

    async def get_stock_info(self, ticker: str) -> Optional[Dict]:
        """Hisse meta verisi (şirket adı, sektör vb.) çeker."""
        cache_key = f"{ticker}:info"
        cached = await cache_manager.get(CacheNamespace.STOCK_INFO, cache_key)
        if cached:
            return cached

        try:
            info = await self.yfinance.get_stock_info(ticker)
            if info:
                await cache_manager.set(CacheNamespace.STOCK_INFO, cache_key, info, ttl=86400)
                return info
        except Exception as e:
            logger.warning("Hisse bilgisi alınamadı.", ticker=ticker, error=str(e))

        return {"ticker": ticker, "company_name": ticker, "source": "default"}

    def _build_fetcher_chain(self):
        """Mevcut API anahtarlarına göre fetcher zinciri oluşturur."""
        chain = []
        if settings.has_polygon:
            chain.append(("polygon", self.polygon))
        if settings.has_alpha_vantage:
            chain.append(("alpha_vantage", self.alpha_vantage))
        chain.append(("yfinance", self.yfinance))  # Her zaman ekle (anahtar gerekmez)
        return chain

    def _get_cache_ttl(self, timeframe: str) -> int:
        """Zaman dilimine göre cache süresi (saniye)."""
        ttl_map = {
            "1d": 300,       # 5 dakika (piyasa açıkken sık güncelle)
            "1h": 120,       # 2 dakika
            "5m": 30,        # 30 saniye
            "1w": 3600,      # 1 saat
            "1mo": 21600,    # 6 saat
        }
        return ttl_map.get(timeframe, 300)


# Singleton
market_data_service = MarketDataService()

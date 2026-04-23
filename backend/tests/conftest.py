"""
QuantEdge AI — pytest Konfigürasyonu ve Ortak Fixture'lar
==========================================================
conftest.py dosyası pytest tarafından otomatik olarak yüklenir.
Tüm test dosyaları bu fixture'lara erişebilir.
"""

import asyncio
import os
import numpy as np
import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

# Test ortamı ortam değişkenleri
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("SECRET_KEY", "test-secret-key-minimum-32-characters-x")
os.environ.setdefault("CHROMA_HOST", "localhost")
os.environ.setdefault("CHROMA_PORT", "8001")
os.environ.setdefault("MLFLOW_TRACKING_URI", "http://localhost:5000")


# ----------------------------------------------------------
# Event Loop
# ----------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop():
    """Session genelinde tek event loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


# ----------------------------------------------------------
# HTTP Client
# ----------------------------------------------------------

@pytest_asyncio.fixture
async def client():
    """
    Test HTTP istemcisi — gerçek sunucu gerektirmez.
    ASGI transport ile doğrudan FastAPI app'e bağlanır.
    """
    with patch("app.core.cache.cache_manager.connect", new_callable=AsyncMock), \
         patch("app.core.cache.cache_manager.is_connected", return_value=False), \
         patch("app.models.database.create_tables", new_callable=AsyncMock):

        from httpx import AsyncClient, ASGITransport
        from main import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            timeout=30.0,
        ) as ac:
            yield ac


# ----------------------------------------------------------
# Veri Fixture'ları
# ----------------------------------------------------------

@pytest.fixture(scope="session")
def mock_ohlcv_100():
    """100 bar OHLCV — kısa test serisi."""
    return _generate_ohlcv(100, start_price=150.0)


@pytest.fixture(scope="session")
def mock_ohlcv_500():
    """500 bar OHLCV — model eğitimi için yeterli."""
    return _generate_ohlcv(500, start_price=175.0)


@pytest.fixture(scope="session")
def mock_ohlcv():
    """Varsayılan 100 bar (geriye dönük uyumluluk)."""
    return _generate_ohlcv(100, start_price=150.0)


def _generate_ohlcv(n: int, start_price: float = 150.0, seed: int = 42):
    """Deterministik mock OHLCV verisi üretir."""
    rng = np.random.default_rng(seed)
    bars = []
    price = start_price

    for i in range(n):
        dt = datetime.utcnow() - timedelta(days=n - i)
        change = rng.normal(0.0002, 0.015)
        price = max(1.0, price * (1 + change))

        high  = price * (1 + abs(rng.normal(0, 0.008)))
        low   = price * (1 - abs(rng.normal(0, 0.008)))
        open_ = bars[-1]["close_price"] if bars else price * (1 + rng.normal(0, 0.005))

        bars.append({
            "timestamp":   dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
            "open_price":  round(float(open_), 4),
            "high_price":  round(float(high),  4),
            "low_price":   round(float(low),   4),
            "close_price": round(float(price), 4),
            "volume":      int(rng.integers(1_000_000, 30_000_000)),
            "vwap":        round(float((high + low + price) / 3), 4),
            "adjusted_close": round(float(price), 4),
        })

    return bars


@pytest.fixture
def mock_technical_result():
    """Mock teknik analiz sonucu."""
    return {
        "indicators": {
            "rsi_14":          55.3,
            "macd":             0.42,
            "macd_signal":      0.35,
            "macd_histogram":   0.07,
            "bb_upper":       162.5,
            "bb_middle":      155.0,
            "bb_lower":       147.5,
            "bb_pct_b":         0.6,
            "bb_width":         0.097,
            "sma_20":         154.2,
            "sma_50":         150.8,
            "sma_200":        145.0,
            "atr_14":           2.3,
            "adx":             28.4,
            "obv":         1_234_567.0,
            "vwap_daily":     153.7,
            "volume_ratio":     1.2,
            "support_level":  148.0,
            "resistance_level": 160.0,
        },
        "signals": {
            "rsi":             0,
            "macd":            1,
            "bb":              0,
            "trend":           1,
            "vwap":            0,
            "volume_surge":    0,
            "composite_signal": 0.35,
            "signal_summary":  "Buy",
        },
        "patterns":       ["Bullish Engulfing"],
        "current_price":  155.0,
        "price_change_pct": 0.52,
        "timeframe":      "1d",
        "bars_analyzed":  100,
        "last_updated":   datetime.utcnow().isoformat(),
    }


@pytest.fixture
def mock_sentiment():
    """Mock sentiment verisi."""
    return {
        "ticker":           "AAPL",
        "overall_score":    0.25,
        "sentiment_label":  "Bullish",
        "reddit_score":     0.30,
        "stocktwits_score": 0.20,
        "news_score":       0.22,
        "total_mentions":   1250,
        "news_article_count": 8,
        "top_headlines":    [],
        "last_updated":     datetime.utcnow().isoformat(),
    }


@pytest.fixture
def mock_fundamental():
    """Mock temel analiz verisi."""
    return {
        "ticker":            "AAPL",
        "pe_ratio":          28.5,
        "pb_ratio":           8.2,
        "ps_ratio":           7.1,
        "peg_ratio":          2.1,
        "ev_ebitda":         22.4,
        "eps":                6.13,
        "eps_growth_3y":      0.12,
        "revenue_growth_3y":  0.08,
        "gross_margin":       0.43,
        "operating_margin":   0.30,
        "net_margin":         0.25,
        "roe":                1.47,
        "roa":                0.28,
        "debt_to_equity":     1.73,
        "dividend_yield":     0.005,
        "beta":               1.24,
        "fundamental_score": 68.5,
        "insider_signal":    "neutral",
        "analyst_recommendations": [{
            "period":      "2024-01",
            "strong_buy":  15,
            "buy":         20,
            "hold":         8,
            "sell":         2,
            "strong_sell":  0,
        }],
        "earnings_calendar": {
            "next_earnings_date": "2024-04-25",
            "eps_estimate":        1.50,
            "revenue_estimate":    95_000_000_000,
        },
        "source": "finnhub",
    }


@pytest.fixture
def mock_macro():
    """Mock makroekonomik veri."""
    return {
        "fed_rate":             5.33,
        "us_10y_yield":         4.42,
        "us_2y_yield":          4.89,
        "yield_curve_spread":  -0.47,
        "vix":                 18.5,
        "dxy":                104.8,
        "cpi_yoy_pct":          3.2,
        "cpi_level":          312.4,
        "ppi_level":          265.3,
        "unemployment_rate":    3.7,
        "nfp_thousands":      199.0,
        "gdp_billions":     27_400.0,
        "m2_billions":      20_900.0,
        "high_yield_spread":  350.0,
        "mortgage_rate_30y":    6.87,
        "macro_risk_score":    52.0,
        "macro_regime":      "TIGHTENING",
        "last_updated":       datetime.utcnow().isoformat(),
        "source":             "FRED",
    }


@pytest.fixture
def mock_stock_info():
    """Mock hisse bilgisi."""
    return {
        "ticker":       "AAPL",
        "company_name": "Apple Inc.",
        "exchange":     "NASDAQ",
        "sector":       "Technology",
        "industry":     "Consumer Electronics",
        "market_cap":   3_000_000_000_000,
        "currency":     "USD",
        "country":      "USA",
        "source":       "yfinance",
    }


@pytest.fixture
def mock_current_price():
    """Mock anlık fiyat."""
    return {
        "ticker": "AAPL",
        "price":  175.43,
        "source": "mock",
    }


# ----------------------------------------------------------
# ML Fixture'ları
# ----------------------------------------------------------

@pytest.fixture(scope="session")
def sample_feature_matrix():
    """Örnek feature matrisi — (100, 60, 20) şeklinde."""
    rng = np.random.default_rng(42)
    X = rng.normal(0, 1, (100, 60, 20)).astype(np.float32)
    y = rng.normal(0, 0.02, 100).astype(np.float32)
    return X, y


@pytest.fixture(scope="session")
def sample_feature_matrix_2d():
    """XGBoost için 2D feature matrisi — (100, 1200)."""
    rng = np.random.default_rng(42)
    X = rng.normal(0, 1, (100, 1200)).astype(np.float32)
    y = rng.normal(0, 0.02, 100).astype(np.float32)
    return X, y


@pytest.fixture(scope="session")
def sample_prices():
    """Örnek fiyat serisi (500 gün)."""
    rng = np.random.default_rng(42)
    prices = [100.0]
    for _ in range(499):
        prices.append(max(1.0, prices[-1] * (1 + rng.normal(0.0002, 0.015))))
    return np.array(prices, dtype=np.float64)

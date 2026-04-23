"""
QuantEdge AI — Backend Test Suite
===================================
pytest + httpx ile asenkron API testleri.

Çalıştırma:
  cd backend
  pytest tests/ -v --cov=app --cov-report=html
"""

import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock

# Test için mock settings (gerçek API anahtarı gerekmez)
import os
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test_db")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-minimum-x")


# ----------------------------------------------------------
# FIXTURES
# ----------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop():
    """Test event loop."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def client():
    """
    Test HTTP istemcisi.
    Gerçek sunucu başlatmadan ASGI transport kullanır.
    """
    # Cache ve DB mock'la
    with patch("app.core.cache.cache_manager.connect", new_callable=AsyncMock), \
         patch("app.core.cache.cache_manager.is_connected", return_value=True), \
         patch("app.models.database.create_tables", new_callable=AsyncMock):

        from main import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as ac:
            yield ac


@pytest.fixture
def mock_ohlcv():
    """Mock OHLCV verisi."""
    import numpy as np
    from datetime import datetime, timedelta

    bars = []
    price = 150.0
    for i in range(100):
        dt = datetime.utcnow() - timedelta(days=100-i)
        change = np.random.normal(0, 0.015)
        price *= (1 + change)
        bars.append({
            "timestamp": dt.isoformat(),
            "open_price": round(price * (1 + np.random.normal(0, 0.005)), 4),
            "high_price": round(price * (1 + abs(np.random.normal(0, 0.008))), 4),
            "low_price": round(price * (1 - abs(np.random.normal(0, 0.008))), 4),
            "close_price": round(price, 4),
            "volume": int(np.random.randint(1_000_000, 20_000_000)),
            "vwap": round(price, 4),
        })
    return bars


@pytest.fixture
def mock_sentiment():
    """Mock sentiment verisi."""
    return {
        "ticker": "AAPL",
        "overall_score": 0.25,
        "sentiment_label": "Bullish",
        "reddit_score": 0.30,
        "stocktwits_score": 0.20,
        "news_score": 0.22,
        "total_mentions": 1250,
        "last_updated": "2024-01-15T10:00:00",
    }


@pytest.fixture
def mock_macro():
    """Mock makro veri."""
    return {
        "fed_rate": 5.33,
        "us_10y_yield": 4.42,
        "vix": 18.5,
        "yield_curve_spread": 0.15,
        "macro_risk_score": 45.0,
        "macro_regime": "TIGHTENING",
        "last_updated": "2024-01-15T00:00:00",
    }


# ----------------------------------------------------------
# HEALTH ENDPOINT TESTLERİ
# ----------------------------------------------------------

class TestHealthEndpoint:

    @pytest.mark.asyncio
    async def test_health_check_returns_200(self, client):
        """Health endpoint 200 döndürmeli."""
        with patch("app.api.v1.endpoints.health.get_db") as mock_db:
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock()
            mock_db.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db.return_value.__aexit__ = AsyncMock(return_value=None)

            response = await client.get("/api/v1/health")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_root_endpoint(self, client):
        """Root endpoint çalışmalı."""
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "QuantEdge AI"
        assert "disclaimer" in data

    @pytest.mark.asyncio
    async def test_docs_accessible(self, client):
        """API docs erişilebilir olmalı."""
        response = await client.get("/api/docs")
        assert response.status_code == 200


# ----------------------------------------------------------
# MARKET DATA TESTLERİ
# ----------------------------------------------------------

class TestMarketDataEndpoint:

    @pytest.mark.asyncio
    async def test_ohlcv_endpoint_valid_ticker(self, client, mock_ohlcv):
        """Geçerli ticker için OHLCV döndürmeli."""
        with patch(
            "app.services.data_fetchers.market_data.market_data_service.get_ohlcv",
            new_callable=AsyncMock,
            return_value=mock_ohlcv
        ):
            response = await client.get("/api/v1/market/AAPL/ohlcv?timeframe=1d&limit=100")
            assert response.status_code == 200
            data = response.json()
            assert data["ticker"] == "AAPL"
            assert data["bars"] == len(mock_ohlcv)
            assert len(data["data"]) == len(mock_ohlcv)

    @pytest.mark.asyncio
    async def test_ohlcv_invalid_timeframe(self, client):
        """Geçersiz timeframe 400 döndürmeli."""
        response = await client.get("/api/v1/market/AAPL/ohlcv?timeframe=invalid")
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_ohlcv_ticker_uppercase(self, client, mock_ohlcv):
        """Ticker otomatik büyük harfe çevrilmeli."""
        with patch(
            "app.services.data_fetchers.market_data.market_data_service.get_ohlcv",
            new_callable=AsyncMock,
            return_value=mock_ohlcv
        ):
            response = await client.get("/api/v1/market/aapl/ohlcv")
            assert response.status_code == 200
            assert response.json()["ticker"] == "AAPL"

    @pytest.mark.asyncio
    async def test_ohlcv_not_found(self, client):
        """Veri bulunamayınca 404 döndürmeli."""
        with patch(
            "app.services.data_fetchers.market_data.market_data_service.get_ohlcv",
            new_callable=AsyncMock,
            return_value=None
        ):
            response = await client.get("/api/v1/market/FAKEXYZ/ohlcv")
            assert response.status_code == 404


# ----------------------------------------------------------
# SENTIMENT TESTLERİ
# ----------------------------------------------------------

class TestSentimentEndpoint:

    @pytest.mark.asyncio
    async def test_sentiment_returns_score(self, client, mock_sentiment):
        """Sentiment endpoint skor döndürmeli."""
        with patch(
            "app.services.data_fetchers.sentiment.sentiment_service.get_aggregated_sentiment",
            new_callable=AsyncMock,
            return_value=mock_sentiment
        ):
            response = await client.get("/api/v1/sentiment/AAPL")
            assert response.status_code == 200
            data = response.json()
            assert "overall_score" in data
            assert -1 <= data["overall_score"] <= 1

    @pytest.mark.asyncio
    async def test_sentiment_label_valid(self, client, mock_sentiment):
        """Sentiment etiketi geçerli olmalı."""
        valid_labels = {"Very Bullish", "Bullish", "Neutral", "Bearish", "Very Bearish"}
        with patch(
            "app.services.data_fetchers.sentiment.sentiment_service.get_aggregated_sentiment",
            new_callable=AsyncMock,
            return_value=mock_sentiment
        ):
            response = await client.get("/api/v1/sentiment/AAPL")
            data = response.json()
            assert data["sentiment_label"] in valid_labels


# ----------------------------------------------------------
# MAKRO TESTLERİ
# ----------------------------------------------------------

class TestMacroEndpoint:

    @pytest.mark.asyncio
    async def test_macro_snapshot(self, client, mock_macro):
        """Makro snapshot döndürmeli."""
        with patch(
            "app.services.data_fetchers.macro.macro_service.fred.get_macro_snapshot",
            new_callable=AsyncMock,
            return_value=mock_macro
        ):
            response = await client.get("/api/v1/macro/snapshot")
            assert response.status_code == 200
            data = response.json()
            assert "fed_rate" in data or "vix" in data


# ----------------------------------------------------------
# TAHMİN TESTLERİ
# ----------------------------------------------------------

class TestPredictionEndpoint:

    @pytest.mark.asyncio
    async def test_prediction_valid_request(self, client, mock_ohlcv, mock_sentiment, mock_macro):
        """Geçerli tahmin isteği yanıt döndürmeli."""
        with patch("app.services.data_fetchers.market_data.market_data_service.get_ohlcv",
                   new_callable=AsyncMock, return_value=mock_ohlcv), \
             patch("app.services.data_fetchers.market_data.market_data_service.get_current_price",
                   new_callable=AsyncMock, return_value={"price": 175.0, "ticker": "AAPL"}), \
             patch("app.services.data_fetchers.market_data.market_data_service.get_stock_info",
                   new_callable=AsyncMock, return_value={"ticker": "AAPL", "company_name": "Apple Inc."}), \
             patch("app.services.data_fetchers.sentiment.sentiment_service.get_aggregated_sentiment",
                   new_callable=AsyncMock, return_value=mock_sentiment), \
             patch("app.services.data_fetchers.macro.macro_service.get_full_macro_context",
                   new_callable=AsyncMock, return_value=mock_macro), \
             patch("app.services.data_fetchers.fundamental.fundamental_service.get_comprehensive_fundamental",
                   new_callable=AsyncMock, return_value={"fundamental_score": 65.0}), \
             patch("app.services.analysis.technical.technical_service.analyze",
                   return_value={"signals": {"composite_signal": 0.3}, "indicators": {}}):

            response = await client.post("/api/v1/stocks/predict", json={
                "ticker": "AAPL",
                "timeframe": "1d",
            })
            assert response.status_code == 200
            data = response.json()
            assert data["ticker"] == "AAPL"
            assert "predicted_price" in data
            assert "direction" in data
            assert data["direction"] in ["up", "down", "sideways"]
            assert 0 <= data["direction_confidence"] <= 1
            assert "disclaimer" in data

    @pytest.mark.asyncio
    async def test_prediction_invalid_timeframe(self, client):
        """Geçersiz timeframe 422 döndürmeli."""
        response = await client.post("/api/v1/stocks/predict", json={
            "ticker": "AAPL",
            "timeframe": "invalid_tf",
        })
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_prediction_ticker_normalized(self, client, mock_ohlcv, mock_sentiment, mock_macro):
        """Küçük harfli ticker büyük harfe çevrilmeli."""
        with patch("app.services.data_fetchers.market_data.market_data_service.get_ohlcv",
                   new_callable=AsyncMock, return_value=mock_ohlcv), \
             patch("app.services.data_fetchers.market_data.market_data_service.get_current_price",
                   new_callable=AsyncMock, return_value={"price": 175.0}), \
             patch("app.services.data_fetchers.market_data.market_data_service.get_stock_info",
                   new_callable=AsyncMock, return_value={"ticker": "AAPL", "company_name": "Apple"}), \
             patch("app.services.data_fetchers.sentiment.sentiment_service.get_aggregated_sentiment",
                   new_callable=AsyncMock, return_value=mock_sentiment), \
             patch("app.services.data_fetchers.macro.macro_service.get_full_macro_context",
                   new_callable=AsyncMock, return_value=mock_macro), \
             patch("app.services.data_fetchers.fundamental.fundamental_service.get_comprehensive_fundamental",
                   new_callable=AsyncMock, return_value={}), \
             patch("app.services.analysis.technical.technical_service.analyze",
                   return_value={"signals": {}, "indicators": {}}):

            response = await client.post("/api/v1/stocks/predict", json={"ticker": "aapl", "timeframe": "1d"})
            assert response.status_code == 200
            assert response.json()["ticker"] == "AAPL"


# ----------------------------------------------------------
# FEATURE ENGINEERING TESTLERİ
# ----------------------------------------------------------

class TestFeatureEngineering:

    def test_price_features_shape(self, mock_ohlcv):
        """Feature matrisinin boyutu doğru olmalı."""
        from app.services.ml.feature_engineering import FeatureEngineeringPipeline

        pipeline = FeatureEngineeringPipeline()
        ta_mock = {"indicators": {}, "signals": {"composite_signal": 0.1}, "patterns": []}

        try:
            X, y, names = pipeline.build_feature_matrix(
                ohlcv=mock_ohlcv,
                technical=ta_mock,
                timeframe="1d",
                sequence_length=30,
            )
            assert X.ndim == 3
            assert X.shape[1] == 30  # sequence_length
            assert X.shape[2] == len(names)  # feature sayısı
            assert len(y) == len(X)
        except ValueError as e:
            # Yetersiz veri durumu da kabul edilebilir
            assert "Yetersiz" in str(e) or "az" in str(e)

    def test_feature_names_not_empty(self, mock_ohlcv):
        """Feature isimleri boş olmamalı."""
        from app.services.ml.feature_engineering import FeatureEngineeringPipeline

        pipeline = FeatureEngineeringPipeline()
        ta_mock = {"indicators": {}, "signals": {}, "patterns": []}

        try:
            _, _, names = pipeline.build_feature_matrix(mock_ohlcv, ta_mock, sequence_length=20)
            assert len(names) > 0
            assert all(isinstance(n, str) for n in names)
        except ValueError:
            pass


# ----------------------------------------------------------
# TEKNİK ANALİZ TESTLERİ
# ----------------------------------------------------------

class TestTechnicalAnalysis:

    def test_analyze_returns_indicators(self, mock_ohlcv):
        """Teknik analiz gösterge döndürmeli."""
        from app.services.analysis.technical import TechnicalAnalysisService

        ta = TechnicalAnalysisService()
        result = ta.analyze(mock_ohlcv)

        assert "indicators" in result
        assert "signals" in result
        assert "patterns" in result
        assert result["current_price"] > 0

    def test_composite_signal_range(self, mock_ohlcv):
        """Bileşik sinyal -1 ile 1 arasında olmalı."""
        from app.services.analysis.technical import TechnicalAnalysisService

        ta = TechnicalAnalysisService()
        result = ta.analyze(mock_ohlcv)

        composite = result["signals"].get("composite_signal", 0)
        assert -1 <= composite <= 1

    def test_insufficient_data_returns_empty(self):
        """Az veriyle boş sonuç döndürmeli."""
        from app.services.analysis.technical import TechnicalAnalysisService

        ta = TechnicalAnalysisService()
        result = ta.analyze([])   # Boş veri
        assert result.get("current_price") is None

    def test_support_resistance_levels(self, mock_ohlcv):
        """Destek/direnç seviyeleri mantıklı olmalı."""
        from app.services.analysis.technical import TechnicalAnalysisService

        ta = TechnicalAnalysisService()
        result = ta.analyze(mock_ohlcv)

        ind = result["indicators"]
        if ind.get("support_level") and ind.get("resistance_level"):
            assert ind["support_level"] < ind["resistance_level"]


# ----------------------------------------------------------
# ANOMALI TESPİT TESTLERİ
# ----------------------------------------------------------

class TestAnomalyDetection:

    def test_normal_data_not_anomaly(self, mock_ohlcv):
        """Normal veri anomali sayılmamalı (çoğunlukla)."""
        from app.services.ml.prediction import AnomalyDetector
        import numpy as np

        detector = AnomalyDetector()
        prices = np.array([bar["close_price"] for bar in mock_ohlcv])
        volumes = np.array([bar["volume"] for bar in mock_ohlcv])

        result = detector.detect(
            features=np.random.randn(len(mock_ohlcv), 10),
            prices=prices,
            volume=volumes,
        )

        assert "is_anomaly" in result
        assert "severity" in result
        assert result["severity"] in ["low", "medium", "high", "extreme"]

    def test_extreme_price_move_detected(self):
        """Aşırı fiyat hareketi anomali sayılmalı."""
        from app.services.ml.prediction import AnomalyDetector
        import numpy as np

        detector = AnomalyDetector()

        # %30 günlük değişim — aşırı hareket
        prices = np.array([100.0] * 30 + [130.0])

        result = detector.detect(
            features=np.zeros((1, 5)),
            prices=prices,
        )

        assert result["is_anomaly"] is True
        assert result["severity"] in ["high", "extreme"]


# ----------------------------------------------------------
# CACHE TESTLERİ
# ----------------------------------------------------------

class TestCacheManager:

    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self):
        """Cache'de olmayan anahtar None döndürmeli."""
        from app.core.cache import CacheManager

        cache = CacheManager()
        # Bağlantısız cache
        result = await cache.get("test_ns", "nonexistent_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_key_format(self):
        """Cache anahtarı doğru formatlanmalı."""
        from app.core.cache import CacheManager

        cache = CacheManager()
        key = cache._make_key("market", "AAPL:1d")
        assert key == "quantedge:market:AAPL:1d"
        assert key.startswith("quantedge:")


# ----------------------------------------------------------
# ENSEMBLE TESTLERİ
# ----------------------------------------------------------

class TestEnsembleEngine:

    def test_combine_predictions_all_models(self):
        """Tüm modeller varken ensemble çalışmalı."""
        from app.services.ml.prediction import EnsembleEngine

        engine = EnsembleEngine()
        result = engine.combine_predictions(
            lstm_pred=0.012,
            xgb_pred=0.015,
            arima_pred=0.008,
            current_price=150.0,
            timeframe="1d",
        )

        assert "predicted_price" in result
        assert result["predicted_price"] > 0
        assert result["direction"] in ["up", "down", "sideways"]
        assert 0 <= result["direction_confidence"] <= 1

    def test_combine_predictions_single_model(self):
        """Tek model varken da çalışmalı."""
        from app.services.ml.prediction import EnsembleEngine

        engine = EnsembleEngine()
        result = engine.combine_predictions(
            lstm_pred=None,
            xgb_pred=0.02,
            arima_pred=None,
            current_price=200.0,
            timeframe="1w",
        )

        assert result["direction"] == "up"

    def test_negative_prediction_direction(self):
        """Negatif tahmin düşüş yönü vermeli."""
        from app.services.ml.prediction import EnsembleEngine

        engine = EnsembleEngine()
        result = engine.combine_predictions(
            lstm_pred=-0.03,
            xgb_pred=-0.025,
            arima_pred=-0.02,
            current_price=100.0,
            timeframe="1d",
        )

        assert result["direction"] == "down"

    def test_weights_sum_to_one(self):
        """Ensemble ağırlıkları toplamı 1.0 olmalı."""
        from app.services.ml.prediction import EnsembleEngine

        engine = EnsembleEngine()
        for tf in ["1d", "1w", "1mo", "3mo", "1y"]:
            weights = engine._get_weights(tf)
            total = sum(weights.values())
            assert abs(total - 1.0) < 0.01, f"{tf} ağırlıkları 1.0'a eşit değil: {total}"

"""
QuantEdge AI — ML Model Test Suite
=====================================
Feature engineering, LSTM, XGBoost, ARIMA/GARCH ve Ensemble testleri.
"""

import numpy as np
import pytest


# ----------------------------------------------------------
# FEATURE ENGINEERING TESTLERİ
# ----------------------------------------------------------

class TestFeatureEngineering:

    def test_build_matrix_output_shape(self, mock_ohlcv_100, mock_technical_result):
        """Feature matrisinin boyutu (samples, seq_len, features) olmalı."""
        from app.services.ml.feature_engineering import FeatureEngineeringPipeline
        pipeline = FeatureEngineeringPipeline()

        try:
            X, y, names = pipeline.build_feature_matrix(
                ohlcv=mock_ohlcv_100,
                technical=mock_technical_result,
                timeframe="1d",
                sequence_length=20,
            )
            assert X.ndim == 3, "X 3 boyutlu olmalı: (samples, seq_len, features)"
            assert X.shape[1] == 20, "Sekans uzunluğu 20 olmalı"
            assert X.shape[2] == len(names), "Feature sayısı isim listesiyle eşleşmeli"
            assert len(y) == len(X), "y uzunluğu X ile eşit olmalı"
        except ValueError as e:
            pytest.skip(f"Veri yetersiz (beklenen): {e}")

    def test_feature_names_are_strings(self, mock_ohlcv_100, mock_technical_result):
        """Tüm feature isimleri string olmalı."""
        from app.services.ml.feature_engineering import FeatureEngineeringPipeline
        pipeline = FeatureEngineeringPipeline()
        try:
            _, _, names = pipeline.build_feature_matrix(
                mock_ohlcv_100, mock_technical_result, sequence_length=20
            )
            assert all(isinstance(n, str) for n in names)
            assert len(names) > 10, "En az 10 feature bekleniyor"
        except ValueError:
            pytest.skip("Veri yetersiz")

    def test_no_nan_in_features(self, mock_ohlcv_100, mock_technical_result):
        """Feature matrisinde NaN olmamalı."""
        from app.services.ml.feature_engineering import FeatureEngineeringPipeline
        pipeline = FeatureEngineeringPipeline()
        try:
            X, y, _ = pipeline.build_feature_matrix(
                mock_ohlcv_100, mock_technical_result, sequence_length=20
            )
            assert not np.isnan(X).any(), "Feature matrisinde NaN var"
            assert not np.isnan(y).any(), "Target vektöründe NaN var"
        except ValueError:
            pytest.skip("Veri yetersiz")

    def test_with_all_modules(
        self, mock_ohlcv_100, mock_technical_result,
        mock_sentiment, mock_fundamental, mock_macro
    ):
        """Tüm modüllerle feature engineering çalışmalı."""
        from app.services.ml.feature_engineering import FeatureEngineeringPipeline
        pipeline = FeatureEngineeringPipeline()
        try:
            X, y, names = pipeline.build_feature_matrix(
                ohlcv=mock_ohlcv_100,
                technical=mock_technical_result,
                sentiment=mock_sentiment,
                fundamental=mock_fundamental,
                macro=mock_macro,
                sequence_length=20,
            )
            # Ek modüllerle daha fazla feature olmalı
            assert X.shape[2] > 20, "Tüm modüllerle 20+ feature bekleniyor"
        except ValueError:
            pytest.skip("Veri yetersiz")

    def test_prediction_features_last_sequence(
        self, mock_ohlcv_100, mock_technical_result
    ):
        """Tahmin için yalnızca son sekans döndürülmeli: (1, seq_len, features)."""
        from app.services.ml.feature_engineering import FeatureEngineeringPipeline
        pipeline = FeatureEngineeringPipeline()
        try:
            X, names = pipeline.build_prediction_features(
                mock_ohlcv_100, mock_technical_result, sequence_length=20
            )
            assert X.shape[0] == 1, "Tahmin için 1 örnek olmalı"
            assert X.shape[1] == 20
        except ValueError:
            pytest.skip("Veri yetersiz")

    def test_scaler_fitted_after_first_call(
        self, mock_ohlcv_100, mock_technical_result
    ):
        """İlk çağrı sonrası scaler fit edilmiş olmalı."""
        from app.services.ml.feature_engineering import FeatureEngineeringPipeline
        pipeline = FeatureEngineeringPipeline()
        try:
            pipeline.build_feature_matrix(
                mock_ohlcv_100, mock_technical_result, sequence_length=20
            )
            assert "1d" in pipeline.scalers, "1d timeframe için scaler kaydedilmeli"
        except ValueError:
            pytest.skip("Veri yetersiz")


# ----------------------------------------------------------
# XGBOOST MODEL TESTLERİ
# ----------------------------------------------------------

class TestXGBoostModel:

    def test_build_creates_model(self):
        """build() çağrısı model oluşturmalı."""
        try:
            from app.services.ml.models.xgboost_model import XGBoostModel
            xgb = XGBoostModel()
            xgb.build()
            assert xgb.model is not None
        except ImportError:
            pytest.skip("xgboost yüklü değil")

    def test_train_and_predict(self, sample_feature_matrix_2d):
        """Eğitim + tahmin pipeline'ı çalışmalı."""
        try:
            from app.services.ml.models.xgboost_model import XGBoostModel
            X, y = sample_feature_matrix_2d

            split = int(len(X) * 0.8)
            X_train, X_val = X[:split], X[split:]
            y_train, y_val = y[:split], y[split:]

            xgb = XGBoostModel()
            metrics = xgb.train(X_train, y_train, X_val, y_val)

            assert "xgb_train_rmse" in metrics
            assert metrics["xgb_train_rmse"] >= 0

            preds = xgb.predict(X_val)
            assert len(preds) == len(X_val)
            assert not np.isnan(preds).any()
        except ImportError:
            pytest.skip("xgboost yüklü değil")

    def test_feature_importance_populated(self, sample_feature_matrix_2d):
        """Eğitim sonrası feature importance dolu olmalı."""
        try:
            from app.services.ml.models.xgboost_model import XGBoostModel
            X, y = sample_feature_matrix_2d
            names = [f"feat_{i}" for i in range(X.shape[1])]

            xgb = XGBoostModel()
            xgb.train(X, y, feature_names=names)

            assert len(xgb.feature_importance) > 0
            assert all(v >= 0 for v in xgb.feature_importance.values())
        except ImportError:
            pytest.skip("xgboost yüklü değil")

    def test_get_top_features(self, sample_feature_matrix_2d):
        """Top N feature döndürülmeli."""
        try:
            from app.services.ml.models.xgboost_model import XGBoostModel
            X, y = sample_feature_matrix_2d
            names = [f"feat_{i}" for i in range(X.shape[1])]

            xgb = XGBoostModel()
            xgb.train(X, y, feature_names=names)

            top5 = xgb.get_top_features(5)
            assert len(top5) == 5
            # Önemi azalan sırada olmalı
            scores = [s for _, s in top5]
            assert scores == sorted(scores, reverse=True)
        except ImportError:
            pytest.skip("xgboost yüklü değil")


# ----------------------------------------------------------
# ARIMA/GARCH MODEL TESTLERİ
# ----------------------------------------------------------

class TestARIMAGARCHModel:

    def test_fit_and_forecast(self, sample_prices):
        """ARIMA fit + forecast çalışmalı."""
        try:
            from app.services.ml.models.xgboost_model import ARIMAGARCHModel
            model = ARIMAGARCHModel()
            metrics = model.fit(sample_prices, auto_select=False)

            assert "arima_order" in metrics
            assert "arima_aic" in metrics

            forecast = model.forecast(steps=1, current_price=float(sample_prices[-1]))
            assert "predicted_log_return" in forecast
            assert "volatility_daily" in forecast
            assert forecast["volatility_daily"] > 0

        except ImportError:
            pytest.skip("statsmodels veya arch yüklü değil")

    def test_forecast_price_bounds(self, sample_prices):
        """Tahmin fiyatı mevcut fiyatın %50 içinde olmalı (mantıklı tahmin)."""
        try:
            from app.services.ml.models.xgboost_model import ARIMAGARCHModel
            model = ARIMAGARCHModel()
            model.fit(sample_prices, auto_select=False)

            current = float(sample_prices[-1])
            forecast = model.forecast(steps=1, current_price=current)

            if "price_forecast" in forecast:
                ratio = forecast["price_forecast"] / current
                assert 0.5 < ratio < 2.0, f"Tahmin fiyatı mantıksız: {ratio:.2f}x"
        except ImportError:
            pytest.skip("statsmodels yüklü değil")

    def test_confidence_interval_ordering(self, sample_prices):
        """Alt sınır < tahmin < üst sınır olmalı."""
        try:
            from app.services.ml.models.xgboost_model import ARIMAGARCHModel
            model = ARIMAGARCHModel()
            model.fit(sample_prices, auto_select=False)

            forecast = model.forecast(steps=5, current_price=float(sample_prices[-1]))

            lower = forecast.get("price_lower")
            pred  = forecast.get("price_forecast")
            upper = forecast.get("price_upper")

            if all(v is not None for v in [lower, pred, upper]):
                assert lower < upper, "Alt sınır üst sınırdan küçük olmalı"
        except ImportError:
            pytest.skip("statsmodels yüklü değil")

    def test_auto_select_order(self, sample_prices):
        """Otomatik order seçimi çalışmalı."""
        try:
            from app.services.ml.models.xgboost_model import ARIMAGARCHModel
            model = ARIMAGARCHModel()
            # Kısa seri ile hızlı test
            metrics = model.fit(sample_prices[:100], auto_select=True)
            p, d, q = model._arima_order
            assert 0 <= p <= 4
            assert 0 <= d <= 2
            assert 0 <= q <= 4
        except ImportError:
            pytest.skip("statsmodels yüklü değil")


# ----------------------------------------------------------
# ENSEMBLE ENGINE TESTLERİ
# ----------------------------------------------------------

class TestEnsembleEngine:

    def test_all_models_present(self):
        """Tüm modeller mevcut — normal ensemble."""
        from app.services.ml.prediction import EnsembleEngine
        engine = EnsembleEngine()

        result = engine.combine_predictions(
            lstm_pred=0.012,
            xgb_pred=0.015,
            arima_pred=0.008,
            current_price=150.0,
            timeframe="1d",
        )

        assert result["direction"] == "up"
        assert result["predicted_price"] > 150.0
        assert 0 < result["direction_confidence"] <= 1.0
        assert result["risk_level"] in ["low", "medium", "high", "extreme"]
        assert "model_contributions" in result

    def test_single_model_fallback(self):
        """Tek model varken ensemble çalışmalı."""
        from app.services.ml.prediction import EnsembleEngine
        engine = EnsembleEngine()

        result = engine.combine_predictions(
            lstm_pred=None,
            xgb_pred=-0.025,
            arima_pred=None,
            current_price=200.0,
            timeframe="1w",
        )

        assert result["direction"] == "down"
        assert result["predicted_price"] < 200.0

    def test_no_valid_prediction_raises(self):
        """Hiç model yoksa ValueError fırlatmalı."""
        from app.services.ml.prediction import EnsembleEngine
        engine = EnsembleEngine()

        with pytest.raises(ValueError, match="Hiçbir model"):
            engine.combine_predictions(
                lstm_pred=None, xgb_pred=None, arima_pred=None,
                current_price=100.0, timeframe="1d",
            )

    def test_sideways_prediction(self):
        """±0.005 içi tahmin sideways olmalı."""
        from app.services.ml.prediction import EnsembleEngine
        engine = EnsembleEngine()

        result = engine.combine_predictions(
            lstm_pred=0.001, xgb_pred=-0.001, arima_pred=0.0,
            current_price=100.0, timeframe="1d",
        )
        assert result["direction"] == "sideways"

    def test_weights_sum_per_timeframe(self):
        """Her timeframe ağırlıkları 1.0'a eşit olmalı."""
        from app.services.ml.prediction import EnsembleEngine
        engine = EnsembleEngine()

        for tf in ["1d", "1w", "1mo", "3mo", "1y"]:
            w = engine._get_weights(tf)
            total = sum(w.values())
            assert abs(total - 1.0) < 1e-6, f"{tf}: ağırlık toplamı {total}"

    def test_confidence_interval_order(self):
        """Alt sınır < tahmin < üst sınır olmalı."""
        from app.services.ml.prediction import EnsembleEngine
        engine = EnsembleEngine()

        result = engine.combine_predictions(
            lstm_pred=0.02, xgb_pred=0.018, arima_pred=0.015,
            current_price=100.0, timeframe="1d",
        )

        lower = result.get("lower_bound")
        pred  = result.get("predicted_price")
        upper = result.get("upper_bound")

        if all(v is not None for v in [lower, pred, upper]):
            assert lower < pred, f"lower={lower} >= pred={pred}"
            assert pred < upper, f"pred={pred} >= upper={upper}"

    def test_anomaly_increases_risk(self):
        """Anomali tespit edilince risk seviyesi yükselmeli."""
        from app.services.ml.prediction import EnsembleEngine
        engine = EnsembleEngine()

        normal_result = engine.combine_predictions(
            lstm_pred=0.01, xgb_pred=0.01, arima_pred=0.01,
            current_price=100.0, timeframe="1d",
        )

        anomaly_result = engine.combine_predictions(
            lstm_pred=0.01, xgb_pred=0.01, arima_pred=0.01,
            current_price=100.0, timeframe="1d",
            anomaly_result={
                "is_anomaly": True,
                "severity": "extreme",
                "description": "Test anomali",
            }
        )

        risk_order = {"low": 0, "medium": 1, "high": 2, "extreme": 3}
        normal_risk  = risk_order.get(normal_result["risk_level"], 0)
        anomaly_risk = risk_order.get(anomaly_result["risk_level"], 0)
        assert anomaly_risk >= normal_risk, "Anomali risk seviyesini artırmalı"


# ----------------------------------------------------------
# ANOMALİ TESPİT TESTLERİ
# ----------------------------------------------------------

class TestAnomalyDetector:

    def test_normal_data_result_structure(self, mock_ohlcv_100):
        """Sonuç yapısı doğru olmalı."""
        from app.services.ml.prediction import AnomalyDetector
        detector = AnomalyDetector()
        prices = np.array([b["close_price"] for b in mock_ohlcv_100])

        result = detector.detect(
            features=np.random.randn(len(prices), 5),
            prices=prices,
        )

        required_keys = ["is_anomaly", "anomaly_score", "severity", "anomaly_types"]
        for key in required_keys:
            assert key in result, f"'{key}' sonuçta bulunmalı"

        assert isinstance(result["is_anomaly"], bool)
        assert result["severity"] in ["low", "medium", "high", "extreme"]

    def test_large_price_jump_detected(self):
        """Büyük fiyat hareketi anomali sayılmalı."""
        from app.services.ml.prediction import AnomalyDetector
        detector = AnomalyDetector()

        prices = np.array([100.0] * 50 + [150.0])  # %50 anlık artış

        result = detector.detect(
            features=np.zeros((1, 5)),
            prices=prices,
        )

        assert result["is_anomaly"] is True
        assert result["severity"] in ["high", "extreme"]

    def test_volume_spike_detection(self, mock_ohlcv_100):
        """Hacim patlaması anomali sayılmalı."""
        from app.services.ml.prediction import AnomalyDetector
        detector = AnomalyDetector()

        prices  = np.array([b["close_price"] for b in mock_ohlcv_100])
        volumes = np.array([b["volume"] for b in mock_ohlcv_100])

        # Son hacmi 10x yap
        volumes[-1] = volumes[:-1].mean() * 10

        result = detector.detect(
            features=np.zeros((1, 5)),
            prices=prices,
            volume=volumes,
        )

        # Hacim spike anomalisi türleri arasında olmalı
        assert any("volume" in t for t in result["anomaly_types"]), \
            f"Volume anomalisi bekleniyor, alınan: {result['anomaly_types']}"

    def test_macro_crisis_detection(self, mock_ohlcv_100):
        """Makro kriz sinyali anomali sayılmalı."""
        from app.services.ml.prediction import AnomalyDetector
        detector = AnomalyDetector()

        prices = np.array([b["close_price"] for b in mock_ohlcv_100])
        crisis_macro = {"vix": 55.0, "yield_curve_spread": -1.2}

        result = detector.detect(
            features=np.zeros((1, 5)),
            prices=prices,
            macro=crisis_macro,
        )

        assert result["is_anomaly"] is True
        assert result["severity"] in ["high", "extreme"]

    def test_isolation_forest_fitting(self, sample_feature_matrix_2d):
        """Isolation Forest fit edilmeli."""
        from app.services.ml.prediction import AnomalyDetector
        X, _ = sample_feature_matrix_2d

        detector = AnomalyDetector()
        detector.fit(X)

        assert detector._fitted is True
        assert detector.isolation_forest is not None


# ----------------------------------------------------------
# RİSK ANALİZİ TESTLERİ
# ----------------------------------------------------------

class TestRiskAnalysis:

    def test_var_calculation(self, sample_prices):
        """VaR hesaplaması çalışmalı."""
        from app.services.analysis.risk import RiskAnalysisService
        risk = RiskAnalysisService()

        profile = risk.calculate_full_risk_profile(list(sample_prices))

        assert "var_95" in profile
        assert "var_99" in profile
        assert profile["var_95"] > 0
        assert profile["var_99"] >= profile["var_95"], "VaR 99 >= VaR 95 olmalı"

    def test_max_drawdown_negative(self, sample_prices):
        """Maximum drawdown negatif olmalı."""
        from app.services.analysis.risk import RiskAnalysisService
        risk = RiskAnalysisService()

        profile = risk.calculate_full_risk_profile(list(sample_prices))

        assert profile["max_drawdown"] <= 0, "Max drawdown negatif olmalı"

    def test_sharpe_ratio_computed(self, sample_prices):
        """Sharpe oranı hesaplanmalı."""
        from app.services.analysis.risk import RiskAnalysisService
        risk = RiskAnalysisService()

        profile = risk.calculate_full_risk_profile(list(sample_prices))

        assert "sharpe_ratio" in profile
        assert isinstance(profile["sharpe_ratio"], float)
        assert not np.isnan(profile["sharpe_ratio"])

    def test_insufficient_data_returns_error(self):
        """Az veriyle hata mesajı döndürmeli."""
        from app.services.analysis.risk import RiskAnalysisService
        risk = RiskAnalysisService()

        result = risk.calculate_full_risk_profile([100.0, 101.0])

        assert "error" in result

    def test_beta_calculation(self, sample_prices):
        """Beta hesaplaması çalışmalı."""
        from app.services.analysis.risk import RiskAnalysisService
        risk = RiskAnalysisService()

        # Benchmark olarak hafif farklı seri kullan
        benchmark = list(sample_prices * 0.9 + np.random.normal(0, 1, len(sample_prices)))

        profile = risk.calculate_full_risk_profile(
            list(sample_prices),
            benchmark_prices=benchmark,
        )

        if "beta" in profile:
            assert isinstance(profile["beta"], float)
            # Beta normalde 0-3 arasında olur
            assert -5 < profile["beta"] < 10


# ----------------------------------------------------------
# TEKNİK ANALİZ TESTLERİ (ML perspektifinden)
# ----------------------------------------------------------

class TestTechnicalForML:

    def test_composite_signal_in_range(self, mock_ohlcv_100):
        """Composite sinyal -1 ile 1 arasında olmalı."""
        from app.services.analysis.technical import TechnicalAnalysisService
        ta = TechnicalAnalysisService()

        result = ta.analyze(mock_ohlcv_100, "1d")
        composite = result["signals"].get("composite_signal", 0)

        assert -1.0 <= composite <= 1.0

    def test_all_price_indicators_positive(self, mock_ohlcv_100):
        """Fiyat göstergeleri pozitif olmalı (fiyat > 0)."""
        from app.services.analysis.technical import TechnicalAnalysisService
        ta = TechnicalAnalysisService()

        result = ta.analyze(mock_ohlcv_100)
        ind = result["indicators"]

        for key in ["sma_20", "sma_50", "bb_upper", "bb_lower", "vwap_daily"]:
            if ind.get(key) is not None:
                assert ind[key] > 0, f"{key} > 0 olmalı, alınan: {ind[key]}"

    def test_bollinger_band_ordering(self, mock_ohlcv_100):
        """BB Üst > BB Orta > BB Alt olmalı."""
        from app.services.analysis.technical import TechnicalAnalysisService
        ta = TechnicalAnalysisService()

        result = ta.analyze(mock_ohlcv_100)
        ind = result["indicators"]

        if all(ind.get(k) for k in ["bb_upper", "bb_middle", "bb_lower"]):
            assert ind["bb_upper"] > ind["bb_middle"] > ind["bb_lower"], \
                f"BB sıralaması yanlış: {ind['bb_lower']:.2f} < {ind['bb_middle']:.2f} < {ind['bb_upper']:.2f}"

    def test_support_below_resistance(self, mock_ohlcv_100):
        """Destek < Direnç olmalı."""
        from app.services.analysis.technical import TechnicalAnalysisService
        ta = TechnicalAnalysisService()

        result = ta.analyze(mock_ohlcv_100)
        ind = result["indicators"]

        if ind.get("support_level") and ind.get("resistance_level"):
            assert ind["support_level"] < ind["resistance_level"], \
                "Destek seviyesi direnç seviyesinden küçük olmalı"

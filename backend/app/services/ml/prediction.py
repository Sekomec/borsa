"""
QuantEdge AI — Ensemble Motor & Anomali Tespiti
=================================================
Ensemble Stratejisi:
  LSTM + XGBoost + ARIMA → Stacking Ensemble

Ağırlıklandırma:
  - Zaman dilimine göre dinamik ağırlıklar
  - Validasyon performansına göre adaptif ağırlık
  - Bayesian Model Averaging (BMA) yaklaşımı

Anomali Tespiti:
  - Isolation Forest: Çok boyutlu anomali tespiti
  - LSTM Autoencoder: Zaman serisi rekonstrüksiyon hatası
  - "Black Swan" uyarı sistemi

Model Explainability:
  - SHAP değerleri ile her tahminin açıklaması
  - "Bu tahmin neden yapıldı?" sorusuna yanıt
"""

import os
import pickle
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import structlog

from app.core.config import settings

logger = structlog.get_logger()


# ----------------------------------------------------------
# ANOMALI TESPİT MOTORU
# ----------------------------------------------------------

class AnomalyDetector:
    """
    Finansal anomali tespiti.

    Yöntemler:
    1. Isolation Forest: Çok boyutlu outlier tespiti
       - "Bu fiyat hareketi istatistiksel olarak anormal mı?"
    2. Z-Score: Basit volatilite bazlı anomali
       - "Bu günün değişimi tarihsel dağılımdan ne kadar uzak?"
    3. LSTM Autoencoder: Zaman serisi rekonstrüksiyon hatası (gelişmiş)
       - "Model bu paterni daha önce hiç görmedi mi?"

    Black Swan Kriterleri:
    - 5+ sigma fiyat hareketi
    - Aşırı hacim patlaması (>5x ortalama)
    - VIX > 40 + negatif yield curve
    """

    def __init__(self):
        self.isolation_forest = None
        self._fitted = False

    def fit(self, feature_matrix: np.ndarray) -> None:
        """Isolation Forest modelini eğitir."""
        try:
            from sklearn.ensemble import IsolationForest
        except ImportError:
            logger.warning("sklearn bulunamadı. Anomali tespiti devre dışı.")
            return

        self.isolation_forest = IsolationForest(
            n_estimators=200,
            contamination=0.05,     # %5 anomali oranı varsayımı
            random_state=42,
            n_jobs=-1,
        )
        self.isolation_forest.fit(feature_matrix)
        self._fitted = True
        logger.info("Anomali dedektörü eğitildi.", samples=len(feature_matrix))

    def detect(
        self,
        features: np.ndarray,
        prices: np.ndarray,
        volume: Optional[np.ndarray] = None,
        macro: Optional[Dict] = None,
    ) -> Dict:
        """
        Anomali tespiti yapar.

        Returns:
            {
              'is_anomaly': bool,
              'anomaly_score': float,  # -1 (normal) ile 0 (anomali arası)
              'anomaly_type': str,
              'severity': str,         # 'low', 'medium', 'high', 'black_swan'
              'description': str,
            }
        """
        anomalies = []
        severity = "none"
        descriptions = []

        # 1. Z-Score anomali (fiyat hareketi)
        if len(prices) >= 20:
            returns = np.diff(np.log(prices))
            if len(returns) > 0:
                recent_return = returns[-1]
                historical_std = np.std(returns[:-1])
                if historical_std > 0:
                    z_score = abs(recent_return / historical_std)
                    if z_score > 5:
                        anomalies.append("extreme_price_move")
                        severity = "black_swan"
                        descriptions.append(
                            f"Aşırı fiyat hareketi tespit edildi ({z_score:.1f} sigma). "
                            f"Bu istatistiksel olarak nadir bir olaydır."
                        )
                    elif z_score > 3:
                        anomalies.append("significant_price_move")
                        severity = "high"
                        descriptions.append(
                            f"Önemli fiyat hareketi ({z_score:.1f} sigma)."
                        )

        # 2. Isolation Forest anomali
        isolation_score = -1.0
        if self._fitted and self.isolation_forest and len(features) > 0:
            try:
                last_features = features[-1:] if features.ndim == 2 else features[-1:, -1, :]
                isolation_pred = self.isolation_forest.predict(last_features)
                isolation_score = float(self.isolation_forest.score_samples(last_features)[0])

                if isolation_pred[0] == -1:
                    anomalies.append("isolation_forest_anomaly")
                    if severity == "none":
                        severity = "medium"
                    descriptions.append("Çok boyutlu anomali: Bu veri noktası tarihsel dağılımdan sapıyor.")
            except Exception as e:
                logger.debug("Isolation Forest hatası.", error=str(e))

        # 3. Hacim anomalisi
        if volume is not None and len(volume) >= 20:
            recent_vol = volume[-1]
            avg_vol = np.mean(volume[-20:])
            if avg_vol > 0:
                vol_ratio = recent_vol / avg_vol
                if vol_ratio > 5:
                    anomalies.append("extreme_volume_spike")
                    if severity not in ["black_swan", "high"]:
                        severity = "high"
                    descriptions.append(
                        f"Aşırı hacim artışı: Ortalama hacmin {vol_ratio:.1f}x üzerinde. "
                        f"Pump/Dump veya büyük kurumsal hareket olabilir."
                    )
                elif vol_ratio > 3:
                    anomalies.append("volume_spike")
                    if severity == "none":
                        severity = "medium"
                    descriptions.append(f"Önemli hacim artışı ({vol_ratio:.1f}x ortalama).")

        # 4. Makro black swan kontrolü
        if macro:
            vix = macro.get("vix", 20)
            ycs = macro.get("yield_curve_spread", 1.0)
            if vix and vix > 40 and ycs and ycs < -0.5:
                anomalies.append("macro_crisis_signal")
                severity = "black_swan"
                descriptions.append(
                    f"Makroekonomik kriz sinyali: VIX={vix:.1f}, "
                    f"Yield Curve={ycs:.2f}%. Aşırı dikkat gereklidir."
                )

        is_anomaly = len(anomalies) > 0

        # Severity mapping
        severity_map = {"none": "low", "low": "low", "medium": "medium",
                        "high": "high", "black_swan": "extreme"}

        return {
            "is_anomaly": is_anomaly,
            "anomaly_score": round(isolation_score, 4),
            "anomaly_types": anomalies,
            "severity": severity_map.get(severity, "low"),
            "description": " | ".join(descriptions) if descriptions else None,
            "risk_warning": is_anomaly and severity in ["high", "black_swan"],
        }


# ----------------------------------------------------------
# ENSEMBLE MOTOR
# ----------------------------------------------------------

class EnsembleEngine:
    """
    Çoklu model sonuçlarını birleştiren ana tahmin motoru.

    Ensemble Stratejisi:
    1. Her model ayrı tahmin üretir
    2. Zaman dilimine göre ağırlıklar belirlenir (config'den)
    3. Validasyon performansına göre ağırlıklar güncellenir
    4. Güven aralığı Monte Carlo Dropout + GARCH ile hesaplanır
    5. Anomali tespiti yapılır
    6. Final tahmin + risk değerlendirmesi döndürülür
    """

    def __init__(self):
        self.anomaly_detector = AnomalyDetector()

    def combine_predictions(
        self,
        lstm_pred: Optional[float],
        xgb_pred: Optional[float],
        arima_pred: Optional[float],
        lstm_uncertainty: Optional[Tuple[float, float, float]] = None,  # (mean, lower, upper)
        arima_forecast: Optional[Dict] = None,
        current_price: float = None,
        timeframe: str = "1d",
        anomaly_result: Optional[Dict] = None,
        val_performance: Optional[Dict] = None,
    ) -> Dict:
        """
        Model tahminlerini birleştirir.

        Args:
            lstm_pred         : LSTM tahmin edilen log-return
            xgb_pred          : XGBoost tahmin edilen log-return
            arima_pred        : ARIMA tahmin edilen log-return
            lstm_uncertainty  : MC Dropout (mean, lower_95, upper_95)
            arima_forecast    : ARIMA tam tahmin paketi
            current_price     : Güncel fiyat
            timeframe         : Zaman dilimi
            anomaly_result    : Anomali tespiti sonucu
            val_performance   : Validasyon RMSE'leri (adaptif ağırlık için)

        Returns:
            Ensemble tahmin sonucu
        """
        # --- Ağırlıkları belirle ---
        weights = self._get_weights(timeframe, val_performance)

        # --- Mevcut tahminleri topla ---
        predictions = {}
        if lstm_pred is not None and not np.isnan(lstm_pred):
            predictions["lstm"] = float(lstm_pred)
        if xgb_pred is not None and not np.isnan(xgb_pred):
            predictions["xgboost"] = float(xgb_pred)
        if arima_pred is not None and not np.isnan(arima_pred):
            predictions["arima"] = float(arima_pred)

        if not predictions:
            raise ValueError("Hiçbir model tahmin üretemedi.")

        # Mevcut modellere göre ağırlıkları normalize et
        available_weight = sum(weights.get(k, 0) for k in predictions)
        if available_weight == 0:
            available_weight = 1
        norm_weights = {k: weights.get(k, 0.33) / available_weight for k in predictions}

        # --- Ağırlıklı ortalama log-return ---
        ensemble_return = sum(v * norm_weights[k] for k, v in predictions.items())

        # --- Ufuk (timeframe) ölçeği ---
        # Model çıktıları log-return varsayımıyla "birim adım" olarak ele alınıyor.
        # Timeframe büyüdükçe (1mo, 3mo, 1y) aynı günlük getiri daha uzun ufukta
        # farklı hedef fiyat üretmelidir. Aksi halde tüm timeframe'ler aynı hedefi verir.
        horizon_steps = {"1d": 1, "1w": 5, "1mo": 21, "3mo": 63, "1y": 252}
        h = horizon_steps.get(timeframe, 1)
        horizon_return = ensemble_return * h

        # --- Fiyat tahmini ---
        if current_price:
            predicted_price = float(current_price * np.exp(horizon_return))
            predicted_return_pct = (predicted_price / current_price - 1) * 100
        else:
            predicted_price = None
            predicted_return_pct = horizon_return * 100

        # --- Güven aralığı ---
        lower_bound, upper_bound = self._calculate_confidence_interval(
            horizon_return,
            current_price,
            lstm_uncertainty,
            arima_forecast,
            timeframe,
        )

        # --- Yön tahmini ---
        direction, confidence = self._determine_direction(
            ensemble_return, predictions, norm_weights
        )

        # --- Risk seviyesi ---
        risk_level = self._assess_risk(
            ensemble_return, timeframe, anomaly_result
        )

        # --- Volatilite tahmini ---
        vol = self._estimate_volatility(arima_forecast, timeframe)

        # --- Model açıklaması ---
        explanation = self._generate_explanation(
            predictions, norm_weights, timeframe, direction
        )

        return {
            "predicted_return": round(ensemble_return, 6),
            "predicted_price": round(predicted_price, 4) if predicted_price else None,
            "predicted_return_pct": round(predicted_return_pct, 4),
            "direction": direction,
            "direction_confidence": round(confidence, 4),
            "lower_bound": round(lower_bound, 4) if lower_bound else None,
            "upper_bound": round(upper_bound, 4) if upper_bound else None,
            "risk_level": risk_level,
            "volatility_estimate": round(vol, 4),
            "anomaly_detected": anomaly_result.get("is_anomaly", False) if anomaly_result else False,
            "anomaly_description": anomaly_result.get("description") if anomaly_result else None,
            "model_contributions": {k: round(v, 6) for k, v in predictions.items()},
            "ensemble_weights": {k: round(v, 4) for k, v in norm_weights.items()},
            "explanation": explanation,
            "model_version": "ensemble_v1.0",
        }

    def _get_weights(
        self,
        timeframe: str,
        val_performance: Optional[Dict] = None,
    ) -> Dict[str, float]:
        """
        Zaman dilimine göre model ağırlıklarını döndürür.

        Kısa vadede: LSTM + XGBoost ağırlıklı (pattern recognition)
        Uzun vadede: ARIMA ağırlıklı (trend + volatilite)
        """
        base_weights = {
            "1d": {"lstm": 0.45, "xgboost": 0.40, "arima": 0.15},
            "1w": {"lstm": 0.40, "xgboost": 0.35, "arima": 0.25},
            "1mo": {"lstm": 0.30, "xgboost": 0.30, "arima": 0.40},
            "3mo": {"lstm": 0.20, "xgboost": 0.25, "arima": 0.55},
            "1y": {"lstm": 0.15, "xgboost": 0.20, "arima": 0.65},
        }

        weights = base_weights.get(timeframe, base_weights["1d"]).copy()

        # Validasyon performansına göre adaptif ağırlık
        if val_performance:
            weights = self._adaptive_weights(weights, val_performance)

        return weights

    def _adaptive_weights(
        self,
        base_weights: Dict[str, float],
        val_performance: Dict[str, float],
    ) -> Dict[str, float]:
        """
        Validasyon RMSE'sine göre ağırlıkları ayarlar.
        Daha iyi performans → daha yüksek ağırlık.
        """
        # RMSE inverse ile ağırlık (düşük RMSE = yüksek ağırlık)
        inverse_rmse = {}
        for model, rmse in val_performance.items():
            if model in base_weights and rmse and rmse > 0:
                inverse_rmse[model] = 1.0 / rmse

        if not inverse_rmse:
            return base_weights

        total = sum(inverse_rmse.values())
        perf_weights = {k: v / total for k, v in inverse_rmse.items()}

        # Base weight ve performans ağırlığını karıştır (0.7 base + 0.3 performans)
        blended = {}
        for model in base_weights:
            base = base_weights[model]
            perf = perf_weights.get(model, base)
            blended[model] = 0.7 * base + 0.3 * perf

        # Normalize
        total = sum(blended.values())
        return {k: v / total for k, v in blended.items()}

    def _calculate_confidence_interval(
        self,
        horizon_return: float,
        current_price: Optional[float],
        lstm_uncertainty: Optional[Tuple],
        arima_forecast: Optional[Dict],
        timeframe: str,
    ) -> Tuple[Optional[float], Optional[float]]:
        """%90 güven aralığını hesaplar."""
        if current_price is None:
            return None, None

        # GARCH'tan gelen volatilite varsa kullan
        if arima_forecast and "volatility_daily" in arima_forecast:
            vol = arima_forecast["volatility_daily"]
        else:
            # Tarihsel volatilite varsayımı (zaman dilimine göre)
            vol_map = {"1d": 0.015, "1w": 0.025, "1mo": 0.05, "3mo": 0.09, "1y": 0.20}
            vol = vol_map.get(timeframe, 0.02)

        # MC Dropout belirsizliği varsa ağırlıkla
        if lstm_uncertainty and len(lstm_uncertainty) == 3:
            _, lstm_lower, lstm_upper = lstm_uncertainty
            lstm_range = lstm_upper - lstm_lower
            vol = max(vol, lstm_range / 2)

        # Zaman dilimine göre ölçekle
        horizon_days = {"1d": 1, "1w": 5, "1mo": 21, "3mo": 63, "1y": 252}
        h = horizon_days.get(timeframe, 1)
        scaled_vol = vol * np.sqrt(h)

        # %90 güven aralığı (1.645 sigma)
        lower = current_price * np.exp(horizon_return - 1.645 * scaled_vol)
        upper = current_price * np.exp(horizon_return + 1.645 * scaled_vol)

        return float(lower), float(upper)

    def _determine_direction(
        self,
        ensemble_return: float,
        predictions: Dict[str, float],
        weights: Dict[str, float],
    ) -> Tuple[str, float]:
        """
        Yön tahmini ve güven skoru hesaplar.

        Güven: Modellerin ne kadarı aynı yönü işaret ediyor.
        """
        # Eşik: ±%0.5 (sideways bölgesi)
        threshold = 0.005

        if ensemble_return > threshold:
            direction = "up"
        elif ensemble_return < -threshold:
            direction = "down"
        else:
            direction = "sideways"

        # Güven: aynı yönü işaret eden modellerin ağırlık toplamı
        agreeing_weight = 0.0
        for model, pred in predictions.items():
            model_dir = "up" if pred > threshold else ("down" if pred < -threshold else "sideways")
            if model_dir == direction:
                agreeing_weight += weights.get(model, 0.33)

        # Mutlak return büyüklüğüne göre güven artır
        magnitude_boost = min(0.2, abs(ensemble_return) * 10)
        confidence = min(0.95, agreeing_weight + magnitude_boost)

        return direction, confidence

    def _assess_risk(
        self,
        ensemble_return: float,
        timeframe: str,
        anomaly_result: Optional[Dict],
    ) -> str:
        """Risk seviyesini değerlendirir."""
        # Anomali varsa en yüksek risk
        if anomaly_result and anomaly_result.get("severity") in ["high", "extreme"]:
            return "extreme" if anomaly_result.get("severity") == "extreme" else "high"

        # Getiri büyüklüğüne göre risk
        abs_return = abs(ensemble_return)
        vol_map = {"1d": 0.015, "1w": 0.025, "1mo": 0.05, "3mo": 0.09, "1y": 0.20}
        expected_vol = vol_map.get(timeframe, 0.02)

        if abs_return > expected_vol * 3:
            return "high"
        elif abs_return > expected_vol * 1.5:
            return "medium"
        else:
            return "low"

    def _estimate_volatility(
        self,
        arima_forecast: Optional[Dict],
        timeframe: str,
    ) -> float:
        """Tahmini günlük volatiliteyi döndürür."""
        if arima_forecast and "volatility_daily" in arima_forecast:
            return arima_forecast["volatility_daily"]
        vol_map = {"1d": 0.015, "1w": 0.022, "1mo": 0.018, "3mo": 0.016, "1y": 0.015}
        return vol_map.get(timeframe, 0.018)

    def _generate_explanation(
        self,
        predictions: Dict[str, float],
        weights: Dict[str, float],
        timeframe: str,
        direction: str,
    ) -> str:
        """Tahmin için insan okunabilir açıklama üretir."""
        lines = []
        dir_text = {"up": "yükseliş", "down": "düşüş", "sideways": "yatay"}.get(direction, direction)
        lines.append(f"Ensemble model {timeframe} için {dir_text} tahmini yapıyor.")

        # Hangi model en yüksek ağırlıklı?
        dominant = max(weights.items(), key=lambda x: x[1])
        lines.append(f"Baskın model: {dominant[0]} (%{dominant[1]*100:.0f} ağırlık).")

        # Modeller arasında uzlaşı
        directions = {k: ("up" if v > 0 else "down") for k, v in predictions.items()}
        if len(set(directions.values())) == 1:
            lines.append("Tüm modeller aynı yönü işaret ediyor (yüksek uzlaşı).")
        else:
            disagreeing = [k for k, d in directions.items() if d != direction]
            if disagreeing:
                lines.append(f"Dikkat: {', '.join(disagreeing)} modeli farklı yön gösteriyor.")

        return " ".join(lines)


# ----------------------------------------------------------
# ANA TAHMİN MOTORU
# ----------------------------------------------------------

class PredictionEngine:
    """
    Tüm ML modellerini orchestrate eden ana tahmin motoru.

    Akış:
    1. Feature mühendisliği
    2. Modelleri yükle / eğit (gerekirse)
    3. Her modelden tahmin al
    4. Anomali tespiti
    5. Ensemble birleştirme
    6. Sonuç + açıklama döndür
    """

    def __init__(self):
        from app.services.ml.feature_engineering import feature_pipeline
        self.feature_pipeline = feature_pipeline
        self.ensemble = EnsembleEngine()
        self.anomaly_detector = AnomalyDetector()
        self._model_cache: Dict = {}  # ticker:timeframe → modeller

    async def predict(
        self,
        ticker: str,
        timeframe: str,
        ohlcv: List[Dict],
        technical: Dict,
        sentiment: Optional[Dict] = None,
        fundamental: Optional[Dict] = None,
        macro: Optional[Dict] = None,
    ) -> Dict:
        """
        Ana tahmin fonksiyonu. Tüm pipeline'ı yürütür.
        """
        import asyncio

        seq_len = settings.LSTM_SEQUENCE_LENGTH
        current_price = float(ohlcv[-1].get("close_price", 100))

        # --- Feature Engineering ---
        try:
            X, feature_names = self.feature_pipeline.build_prediction_features(
                ohlcv, technical, sentiment, fundamental, macro, timeframe, seq_len
            )
            # XGBoost için son satır (2D)
            X_2d = X.reshape(X.shape[0], -1)
        except Exception as e:
            logger.warning("Feature engineering hatası.", error=str(e))
            X, X_2d, feature_names = None, None, []

        prices_array = np.array([bar["close_price"] for bar in ohlcv])
        volume_array = np.array([bar.get("volume", 0) for bar in ohlcv])

        # --- LSTM Tahmini ---
        lstm_pred = None
        lstm_uncertainty = None
        if X is not None:
            try:
                from app.services.ml.models.lstm_model import LSTMModel
                lstm = LSTMModel()
                if lstm.load(ticker, timeframe):
                    lstm_mean, lstm_lower, lstm_upper = lstm.predict_with_uncertainty(X)
                    lstm_pred = float(lstm_mean[0])
                    lstm_uncertainty = (lstm_pred, float(lstm_lower[0]), float(lstm_upper[0]))
                    logger.debug("LSTM tahmini alındı.", ticker=ticker, pred=lstm_pred)
            except Exception as e:
                logger.warning("LSTM tahmin hatası.", error=str(e))

        # --- XGBoost Tahmini ---
        xgb_pred = None
        if X_2d is not None:
            try:
                from app.services.ml.models.xgboost_model import XGBoostModel
                xgb = XGBoostModel()
                if xgb.load(ticker, timeframe):
                    xgb_pred = float(xgb.predict(X_2d)[0])
                    logger.debug("XGBoost tahmini alındı.", ticker=ticker, pred=xgb_pred)
            except Exception as e:
                logger.warning("XGBoost tahmin hatası.", error=str(e))

        # --- ARIMA/GARCH Tahmini ---
        arima_pred = None
        arima_forecast = None
        try:
            from app.services.ml.models.xgboost_model import ARIMAGARCHModel
            arima = ARIMAGARCHModel()
            if arima.load(ticker, timeframe):
                horizon = {"1d": 1, "1w": 5, "1mo": 21, "3mo": 63, "1y": 252}.get(timeframe, 1)
                arima_forecast = arima.forecast(steps=horizon, current_price=current_price)
                arima_pred = arima_forecast.get("predicted_log_return", 0)
                logger.debug("ARIMA tahmini alındı.", ticker=ticker, pred=arima_pred)
        except Exception as e:
            logger.warning("ARIMA tahmin hatası.", error=str(e))

        # --- Eğitilmiş model yoksa hızlı eğit ---
        if lstm_pred is None and xgb_pred is None and arima_pred is None:
            logger.info("Eğitilmiş model bulunamadı. Hızlı ARIMA eğitimi başlıyor.", ticker=ticker)
            try:
                from app.services.ml.models.xgboost_model import ARIMAGARCHModel
                arima = ARIMAGARCHModel()
                arima.fit(prices_array)
                horizon = {"1d": 1, "1w": 5, "1mo": 21, "3mo": 63, "1y": 252}.get(timeframe, 1)
                arima_forecast = arima.forecast(steps=horizon, current_price=current_price)
                arima_pred = arima_forecast.get("predicted_log_return", 0)
            except Exception as e:
                logger.warning("Hızlı ARIMA eğitimi başarısız.", error=str(e))
                # Son çare: teknik sinyalden basit tahmin
                composite = technical.get("signals", {}).get("composite_signal", 0) or 0
                arima_pred = composite * 0.01  # %1'e çevir

        # --- Anomali Tespiti ---
        anomaly_result = self.anomaly_detector.detect(
            features=X_2d if X_2d is not None else np.array([[0]]),
            prices=prices_array,
            volume=volume_array,
            macro=macro,
        )

        # --- Ensemble Birleştirme ---
        ensemble_result = self.ensemble.combine_predictions(
            lstm_pred=lstm_pred,
            xgb_pred=xgb_pred,
            arima_pred=arima_pred,
            lstm_uncertainty=lstm_uncertainty,
            arima_forecast=arima_forecast,
            current_price=current_price,
            timeframe=timeframe,
            anomaly_result=anomaly_result,
        )

        # MLflow loglama (arka planda)
        await self._log_to_mlflow(ticker, timeframe, ensemble_result)

        return ensemble_result

    async def _log_to_mlflow(
        self, ticker: str, timeframe: str, result: Dict
    ) -> None:
        """Tahmin sonucunu MLflow'a loglar."""
        try:
            import mlflow
            mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
            mlflow.set_experiment(settings.MLFLOW_EXPERIMENT_NAME)

            with mlflow.start_run(run_name=f"predict_{ticker}_{timeframe}_{datetime.utcnow().strftime('%Y%m%d')}"):
                mlflow.log_params({
                    "ticker": ticker,
                    "timeframe": timeframe,
                    "direction": result.get("direction"),
                })
                mlflow.log_metrics({
                    "predicted_return": result.get("predicted_return", 0),
                    "direction_confidence": result.get("direction_confidence", 0),
                    "volatility_estimate": result.get("volatility_estimate", 0),
                })
        except Exception as e:
            logger.debug("MLflow loglama hatası (non-critical).", error=str(e))


# Singleton
prediction_engine = PredictionEngine()

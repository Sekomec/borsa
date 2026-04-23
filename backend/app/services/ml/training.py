"""
QuantEdge AI — Model Eğitim Pipeline'ı (MLflow Entegrasyonlu)
===============================================================
Eğitim Akışı:
  1. Veri çek (market_data + tüm modüller)
  2. Feature engineering
  3. Train/Validation/Test split (zaman serisi için sıralı)
  4. Her modeli eğit (LSTM, XGBoost, ARIMA)
  5. Metrikler + artifacts MLflow'a yükle
  6. Modeli kaydet

Zaman Serisi Train/Val/Test Split:
  ❌ Random split kullanma (data leakage!)
  ✅ Kronolojik sıralı split:
     Train : İlk %70
     Val   : Sonraki %15
     Test  : Son %15

MLOps Özellikleri:
  - Her run MLflow'da track edilir
  - Model versioning (champion/challenger)
  - Otomatik model karşılaştırma
  - Haftalık yeniden eğitim (celery beat)
"""

import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import structlog

from app.core.config import settings

logger = structlog.get_logger()


class ModelTrainer:
    """
    Tüm ML modellerini eğiten ve yöneten sınıf.
    MLflow ile tam entegrasyon.
    """

    def __init__(self):
        from app.services.ml.feature_engineering import feature_pipeline
        self.feature_pipeline = feature_pipeline

    def train_all_models(
        self,
        ticker: str,
        timeframe: str,
        ohlcv: List[Dict],
        technical: Dict,
        sentiment: Optional[Dict] = None,
        fundamental: Optional[Dict] = None,
        macro: Optional[Dict] = None,
        optimize_hyperparams: bool = False,
    ) -> Dict:
        """
        Belirtilen hisse ve timeframe için tüm modelleri eğitir.

        Args:
            ticker              : Hisse kodu
            timeframe           : Tahmin zaman dilimi
            ohlcv               : OHLCV verisi
            technical           : Teknik analiz sonuçları
            sentiment/fund/macro: Ek modüller
            optimize_hyperparams: Optuna ile hyperparametre araması

        Returns:
            Eğitim sonuçları ve metrikleri
        """
        logger.info("Model eğitimi başlıyor.", ticker=ticker, timeframe=timeframe)

        # --- MLflow Run Başlat ---
        try:
            import mlflow
            mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
            mlflow.set_experiment(f"{settings.MLFLOW_EXPERIMENT_NAME}_{ticker}")
            mlflow_active = True
        except Exception:
            mlflow_active = False
            logger.warning("MLflow bağlantısı kurulamadı. Yerel eğitim devam ediyor.")

        seq_len = settings.LSTM_SEQUENCE_LENGTH
        results = {
            "ticker": ticker,
            "timeframe": timeframe,
            "trained_at": datetime.utcnow().isoformat(),
            "models": {},
        }

        run_context = None
        try:
            if mlflow_active:
                import mlflow
                run_context = mlflow.start_run(
                    run_name=f"train_{ticker}_{timeframe}_{datetime.utcnow().strftime('%Y%m%d_%H%M')}"
                )
                run_context.__enter__()
                mlflow.log_params({
                    "ticker": ticker,
                    "timeframe": timeframe,
                    "seq_length": seq_len,
                    "ohlcv_bars": len(ohlcv),
                    "has_sentiment": sentiment is not None,
                    "has_fundamental": fundamental is not None,
                    "has_macro": macro is not None,
                    "optimize_hyperparams": optimize_hyperparams,
                })

            # --- Feature Matrix ---
            try:
                X, y, feature_names = self.feature_pipeline.build_feature_matrix(
                    ohlcv, technical, sentiment, fundamental, macro,
                    timeframe, seq_len
                )
                logger.info(
                    "Feature matrisi hazır.",
                    X_shape=X.shape, y_shape=y.shape,
                    n_features=len(feature_names),
                )
            except Exception as e:
                logger.error("Feature engineering başarısız.", error=str(e))
                return {**results, "error": str(e)}

            # --- Train/Val/Test Split ---
            X_train, X_val, X_test, y_train, y_val, y_test = self._time_series_split(X, y)
            # XGBoost için 2D reshape
            X_train_2d = X_train.reshape(X_train.shape[0], -1)
            X_val_2d = X_val.reshape(X_val.shape[0], -1)
            X_test_2d = X_test.reshape(X_test.shape[0], -1)

            logger.info(
                "Train/Val/Test split tamamlandı.",
                train=len(X_train), val=len(X_val), test=len(X_test),
            )

            mlflow_run = run_context if mlflow_active else None

            # --- LSTM Eğitimi ---
            lstm_metrics = self._train_lstm(
                ticker, timeframe,
                X_train, y_train, X_val, y_val, X_test, y_test,
                mlflow_run=mlflow_run,
            )
            results["models"]["lstm"] = lstm_metrics

            # --- XGBoost Eğitimi ---
            xgb_metrics = self._train_xgboost(
                ticker, timeframe,
                X_train_2d, y_train, X_val_2d, y_val, X_test_2d, y_test,
                feature_names=feature_names,
                optimize_hyperparams=optimize_hyperparams,
                mlflow_run=mlflow_run,
            )
            results["models"]["xgboost"] = xgb_metrics

            # --- ARIMA/GARCH Eğitimi ---
            arima_metrics = self._train_arima(
                ticker, timeframe,
                ohlcv,
                mlflow_run=mlflow_run,
            )
            results["models"]["arima_garch"] = arima_metrics

            # --- Anomali Dedektörü Eğitimi ---
            from app.services.ml.prediction import AnomalyDetector
            detector = AnomalyDetector()
            detector.fit(X_train_2d)
            anomaly_path = os.path.join(
                settings.MODEL_ARTIFACTS_PATH, "anomaly", ticker, f"{timeframe}.pkl"
            )
            os.makedirs(os.path.dirname(anomaly_path), exist_ok=True)
            import pickle
            with open(anomaly_path, "wb") as f:
                pickle.dump(detector, f)

            # --- Final Özet ---
            results["status"] = "success"
            results["best_models"] = self._rank_models(results["models"])

            logger.info(
                "Tüm modeller başarıyla eğitildi.",
                ticker=ticker, timeframe=timeframe,
                best_model=results["best_models"][0] if results["best_models"] else "unknown",
            )

            if mlflow_active and run_context:
                import mlflow
                mlflow.log_dict(results, "training_summary.json")

        except Exception as e:
            results["status"] = "error"
            results["error"] = str(e)
            logger.error("Model eğitimi başarısız.", ticker=ticker, error=str(e))
        finally:
            if mlflow_active and run_context:
                try:
                    run_context.__exit__(None, None, None)
                except Exception:
                    pass

        return results

    def _train_lstm(
        self,
        ticker: str, timeframe: str,
        X_train, y_train, X_val, y_val, X_test, y_test,
        mlflow_run=None,
    ) -> Dict:
        """LSTM modelini eğitir ve değerlendirir."""
        try:
            from app.services.ml.models.lstm_model import LSTMModel
            lstm = LSTMModel()
            lstm.build(X_train.shape[2])

            train_metrics = lstm.train(
                X_train, y_train, X_val, y_val,
                mlflow_run=mlflow_run,
            )

            # Test set değerlendirme
            test_preds = lstm.predict(X_test)
            test_rmse = float(np.sqrt(np.mean((y_test - test_preds) ** 2)))
            test_mae = float(np.mean(np.abs(y_test - test_preds)))

            # Yön doğruluğu
            direction_acc = float(np.mean(np.sign(y_test) == np.sign(test_preds)))

            # Modeli kaydet
            lstm.save(ticker, timeframe)

            metrics = {
                **train_metrics,
                "test_rmse": test_rmse,
                "test_mae": test_mae,
                "direction_accuracy": direction_acc,
                "status": "success",
            }
            logger.info("LSTM eğitimi tamamlandı.", ticker=ticker, **{k: round(v, 4) for k, v in metrics.items() if isinstance(v, float)})
            return metrics

        except Exception as e:
            logger.warning("LSTM eğitimi başarısız.", error=str(e))
            return {"status": "failed", "error": str(e)}

    def _train_xgboost(
        self,
        ticker: str, timeframe: str,
        X_train, y_train, X_val, y_val, X_test, y_test,
        feature_names: List[str] = None,
        optimize_hyperparams: bool = False,
        mlflow_run=None,
    ) -> Dict:
        """XGBoost modelini eğitir ve değerlendirir."""
        try:
            from app.services.ml.models.xgboost_model import XGBoostModel
            xgb = XGBoostModel()

            train_metrics = xgb.train(
                X_train, y_train, X_val, y_val,
                feature_names=feature_names,
                optimize_hyperparams=optimize_hyperparams,
                mlflow_run=mlflow_run,
            )

            # Test değerlendirme
            test_preds = xgb.predict(X_test)
            test_rmse = float(np.sqrt(np.mean((y_test - test_preds) ** 2)))
            test_mae = float(np.mean(np.abs(y_test - test_preds)))
            direction_acc = float(np.mean(np.sign(y_test) == np.sign(test_preds)))

            # Top features
            top_features = xgb.get_top_features(5)

            xgb.save(ticker, timeframe)

            metrics = {
                **train_metrics,
                "test_rmse": test_rmse,
                "test_mae": test_mae,
                "direction_accuracy": direction_acc,
                "top_features": [f[0] for f in top_features],
                "status": "success",
            }
            logger.info("XGBoost eğitimi tamamlandı.", ticker=ticker, test_rmse=test_rmse)
            return metrics

        except Exception as e:
            logger.warning("XGBoost eğitimi başarısız.", error=str(e))
            return {"status": "failed", "error": str(e)}

    def _train_arima(
        self,
        ticker: str, timeframe: str,
        ohlcv: List[Dict],
        mlflow_run=None,
    ) -> Dict:
        """ARIMA+GARCH modelini eğitir."""
        try:
            from app.services.ml.models.xgboost_model import ARIMAGARCHModel
            prices = np.array([bar["close_price"] for bar in ohlcv])

            arima = ARIMAGARCHModel()
            train_metrics = arima.fit(prices, auto_select=True, mlflow_run=mlflow_run)
            arima.save(ticker, timeframe)

            return {**train_metrics, "status": "success"}

        except Exception as e:
            logger.warning("ARIMA eğitimi başarısız.", error=str(e))
            return {"status": "failed", "error": str(e)}

    def _time_series_split(
        self,
        X: np.ndarray,
        y: np.ndarray,
        train_ratio: float = 0.70,
        val_ratio: float = 0.15,
    ) -> Tuple:
        """
        Zaman serisi için sıralı train/val/test split.
        Veri sızıntısını (data leakage) önler.
        """
        n = len(X)
        train_end = int(n * train_ratio)
        val_end = int(n * (train_ratio + val_ratio))

        X_train, y_train = X[:train_end], y[:train_end]
        X_val, y_val = X[train_end:val_end], y[train_end:val_end]
        X_test, y_test = X[val_end:], y[val_end:]

        return X_train, X_val, X_test, y_train, y_val, y_test

    def _rank_models(self, models_result: Dict) -> List[str]:
        """Test RMSE'ye göre modelleri sıralar."""
        ranked = []
        for name, metrics in models_result.items():
            if metrics.get("status") == "success" and "test_rmse" in metrics:
                ranked.append((name, metrics["test_rmse"]))
        ranked.sort(key=lambda x: x[1])
        return [r[0] for r in ranked]


# Singleton
model_trainer = ModelTrainer()

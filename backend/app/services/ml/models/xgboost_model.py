"""
QuantEdge AI — XGBoost & ARIMA/GARCH Modelleri
================================================
XGBoost:
  - Gradient boosted trees
  - Kısa/orta vadeli tahmin için güçlü
  - Feature importance ile yorumlanabilirlik
  - Optuna ile hiperparametre optimizasyonu

ARIMA/GARCH:
  - ARIMA: Otoregresif zaman serisi (ortalama modeli)
  - GARCH: Volatilite modellemesi (variance modeli)
  - Uzun vadeli trend ve volatilite tahmini için
"""

import os
import pickle
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import structlog

from app.core.config import settings

logger = structlog.get_logger()


# ----------------------------------------------------------
# XGBOOST MODELİ
# ----------------------------------------------------------

class XGBoostModel:
    """
    XGBoost tabanlı hisse fiyat tahmin modeli.

    XGBoost'un avantajları:
    - LSTM'e göre çok daha hızlı eğitim
    - Feature importance ile yorumlanabilir
    - Overfitting'e karşı regularization
    - Eksik veriyi handle eder

    Feature importance output, kullanıcıya "bu tahmin neden yapıldı?"
    sorusunu yanıtlamaya yardımcı olur (model explainability).
    """

    def __init__(self):
        self.model = None
        self.feature_names: List[str] = []
        self.feature_importance: Dict[str, float] = {}

    def build(self) -> None:
        """XGBoost regressor oluşturur."""
        try:
            import xgboost as xgb
        except ImportError:
            raise ImportError("xgboost kütüphanesi bulunamadı: pip install xgboost")

        self.model = xgb.XGBRegressor(
            n_estimators=settings.XGBOOST_N_ESTIMATORS,
            max_depth=settings.XGBOOST_MAX_DEPTH,
            learning_rate=settings.XGBOOST_LEARNING_RATE,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_weight=3,
            reg_alpha=0.1,      # L1 regularization
            reg_lambda=1.0,     # L2 regularization
            objective="reg:squarederror",
            eval_metric=["rmse", "mae"],
            random_state=42,
            n_jobs=-1,          # Tüm CPU core'ları kullan
            tree_method="hist", # Hızlı histogram tabanlı
            early_stopping_rounds=50,
        )
        logger.info("XGBoost modeli oluşturuldu.")

    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
        feature_names: Optional[List[str]] = None,
        optimize_hyperparams: bool = False,
        mlflow_run=None,
    ) -> Dict:
        """
        XGBoost modelini eğitir.

        Args:
            X_train            : (samples, features) — 2D (LSTM'den farklı)
            y_train            : (samples,) hedef getiri
            X_val              : Validasyon seti
            y_val              : Validasyon hedefi
            feature_names      : Özellik isimleri
            optimize_hyperparams: Optuna ile hiperparametre araması
            mlflow_run         : MLflow run

        Returns:
            Eğitim metrikleri
        """
        if self.model is None:
            self.build()

        self.feature_names = feature_names or [f"f_{i}" for i in range(X_train.shape[1])]

        if optimize_hyperparams:
            logger.info("Optuna hiperparametre optimizasyonu başlıyor...")
            best_params = self._optimize_with_optuna(X_train, y_train, X_val, y_val)
            self._apply_hyperparams(best_params)
            if mlflow_run:
                try:
                    import mlflow
                    mlflow.log_params({f"xgb_{k}": v for k, v in best_params.items()})
                except Exception:
                    pass

        eval_set = [(X_train, y_train)]
        if X_val is not None and y_val is not None:
            eval_set.append((X_val, y_val))

        self.model.fit(
            X_train, y_train,
            eval_set=eval_set,
            verbose=False,
        )

        # Feature importance
        self.feature_importance = dict(
            zip(self.feature_names, self.model.feature_importances_)
        )

        # Eğitim metrikleri
        train_pred = self.model.predict(X_train)
        train_rmse = float(np.sqrt(np.mean((y_train - train_pred) ** 2)))
        train_mae = float(np.mean(np.abs(y_train - train_pred)))

        metrics = {
            "xgb_train_rmse": train_rmse,
            "xgb_train_mae": train_mae,
            "xgb_n_estimators_used": self.model.best_iteration or settings.XGBOOST_N_ESTIMATORS,
        }

        if X_val is not None:
            val_pred = self.model.predict(X_val)
            metrics["xgb_val_rmse"] = float(np.sqrt(np.mean((y_val - val_pred) ** 2)))
            metrics["xgb_val_mae"] = float(np.mean(np.abs(y_val - val_pred)))

        if mlflow_run:
            try:
                import mlflow
                mlflow.log_metrics(metrics)
                # Top 10 önemli özellik
                top_features = sorted(
                    self.feature_importance.items(), key=lambda x: x[1], reverse=True
                )[:10]
                mlflow.log_params({f"top_feat_{i+1}": f[0] for i, f in enumerate(top_features)})
            except Exception as e:
                logger.warning("MLflow XGBoost loglama hatası.", error=str(e))

        logger.info("XGBoost eğitimi tamamlandı.", **metrics)
        return metrics

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Getiri tahmini yapar. X: (samples, features)"""
        if self.model is None:
            raise RuntimeError("Model henüz eğitilmedi.")
        return self.model.predict(X)

    def get_top_features(self, n: int = 10) -> List[Tuple[str, float]]:
        """En önemli N özelliği döndürür."""
        sorted_features = sorted(
            self.feature_importance.items(),
            key=lambda x: x[1], reverse=True
        )
        return sorted_features[:n]

    def _optimize_with_optuna(
        self,
        X_train, y_train,
        X_val, y_val,
        n_trials: int = 30,
    ) -> Dict:
        """
        Optuna ile Bayesian hiperparametre optimizasyonu.
        Random search'ten 3-5x daha verimli.
        """
        try:
            import optuna
            import xgboost as xgb
            optuna.logging.set_verbosity(optuna.logging.WARNING)
        except ImportError:
            logger.warning("Optuna bulunamadı, varsayılan hiperparametreler kullanılıyor.")
            return {}

        def objective(trial):
            params = {
                "n_estimators": trial.suggest_int("n_estimators", 100, 1000),
                "max_depth": trial.suggest_int("max_depth", 3, 10),
                "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.1, log=True),
                "subsample": trial.suggest_float("subsample", 0.6, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
                "reg_alpha": trial.suggest_float("reg_alpha", 0, 1.0),
                "reg_lambda": trial.suggest_float("reg_lambda", 0.1, 5.0),
                "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
            }
            model = xgb.XGBRegressor(**params, random_state=42, n_jobs=-1, verbosity=0)
            model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
            preds = model.predict(X_val)
            return float(np.sqrt(np.mean((y_val - preds) ** 2)))

        study = optuna.create_study(direction="minimize")
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

        logger.info(
            "Optuna optimizasyonu tamamlandı.",
            best_rmse=study.best_value,
            trials=n_trials,
        )
        return study.best_params

    def _apply_hyperparams(self, params: Dict) -> None:
        """Bulunan en iyi hiperparametreleri uygular."""
        import xgboost as xgb
        self.model = xgb.XGBRegressor(
            **params,
            objective="reg:squarederror",
            random_state=42,
            n_jobs=-1,
            tree_method="hist",
        )

    def save(self, ticker: str, timeframe: str) -> str:
        """Modeli pickle ile kaydeder."""
        if self.model is None:
            raise RuntimeError("Kaydedilecek model yok.")

        path = os.path.join(
            settings.MODEL_ARTIFACTS_PATH,
            "xgboost",
            ticker,
            f"{timeframe}.pkl",
        )
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({
                "model": self.model,
                "feature_names": self.feature_names,
                "feature_importance": self.feature_importance,
            }, f)
        logger.info("XGBoost modeli kaydedildi.", path=path)
        return path

    def load(self, ticker: str, timeframe: str) -> bool:
        """Kaydedilmiş XGBoost modelini yükler."""
        try:
            path = os.path.join(
                settings.MODEL_ARTIFACTS_PATH,
                "xgboost",
                ticker,
                f"{timeframe}.pkl",
            )
            if not os.path.exists(path):
                return False
            with open(path, "rb") as f:
                data = pickle.load(f)
            self.model = data["model"]
            self.feature_names = data.get("feature_names", [])
            self.feature_importance = data.get("feature_importance", {})
            logger.info("XGBoost modeli yüklendi.", ticker=ticker, timeframe=timeframe)
            return True
        except Exception as e:
            logger.warning("XGBoost model yükleme hatası.", error=str(e))
            return False


# ----------------------------------------------------------
# ARIMA / GARCH MODELİ
# ----------------------------------------------------------

class ARIMAGARCHModel:
    """
    ARIMA (ortalama) + GARCH (volatilite) zaman serisi modeli.

    ARIMA(p,d,q):
      p = otoregresif terim (AR): geçmiş değerlerin etkisi
      d = fark alma derecesi (I): stationarity için
      q = hareketli ortalama terimi (MA): hata terimlerinin etkisi

    GARCH(1,1):
      Volatilitenin kümelenmesini yakalar.
      Yüksek volatilite dönemleri yüksek volatiliteye yol açar.
      Risk/güven aralığı tahmini için kullanılır.

    Neden hem ARIMA hem GARCH?
      ARIMA ortalama getiriyi tahmin eder.
      GARCH bu tahminin etrafındaki belirsizliği ölçer.
      Birleşim: nokta tahmini + güven aralığı.
    """

    def __init__(self):
        self.arima_model = None
        self.garch_model = None
        self.arima_fitted = None
        self.garch_fitted = None
        self._arima_order = (1, 1, 1)
        self._garch_order = (1, 1)

    def fit(
        self,
        prices: np.ndarray,
        auto_select: bool = True,
        mlflow_run=None,
    ) -> Dict:
        """
        ARIMA + GARCH modellerini eğitir.

        Args:
            prices     : Kapanış fiyatları dizisi
            auto_select: AIC/BIC ile otomatik order seçimi
            mlflow_run : MLflow run

        Returns:
            Eğitim metrikleri
        """
        try:
            from statsmodels.tsa.statespace.sarimax import SARIMAX
            from arch import arch_model
        except ImportError:
            raise ImportError("statsmodels ve arch kütüphaneleri gerekli.")

        # Log getiriler (stationarity için)
        log_returns = np.diff(np.log(prices)) * 100  # % cinsinden

        # --- ARIMA Order Seçimi ---
        if auto_select:
            self._arima_order = self._select_arima_order(log_returns)

        logger.info(
            "ARIMA eğitiliyor.",
            order=self._arima_order,
            samples=len(log_returns),
        )

        # --- ARIMA Fit ---
        try:
            p, d, q = self._arima_order
            arima = SARIMAX(
                log_returns,
                order=(p, d, q),
                trend="c",
                enforce_stationarity=False,
                enforce_invertibility=False,
            )
            self.arima_fitted = arima.fit(disp=False, maxiter=200)
            arima_aic = float(self.arima_fitted.aic)
            arima_bic = float(self.arima_fitted.bic)
        except Exception as e:
            logger.warning("ARIMA fit hatası, basit AR(1) kullanılıyor.", error=str(e))
            self._arima_order = (1, 0, 0)
            arima = SARIMAX(log_returns, order=(1, 0, 0))
            self.arima_fitted = arima.fit(disp=False)
            arima_aic = float(self.arima_fitted.aic)
            arima_bic = float(self.arima_fitted.bic)

        # ARIMA artıkları al
        residuals = self.arima_fitted.resid

        # --- GARCH(1,1) Fit ---
        logger.info("GARCH(1,1) eğitiliyor.")
        try:
            garch = arch_model(
                residuals,
                vol="Garch",
                p=1, q=1,
                dist="t",        # Student-t dağılımı (fat tails)
                rescale=True,
            )
            self.garch_fitted = garch.fit(
                disp="off",
                show_warning=False,
            )
        except Exception as e:
            logger.warning("GARCH fit hatası.", error=str(e))
            self.garch_fitted = None

        metrics = {
            "arima_order": str(self._arima_order),
            "arima_aic": arima_aic,
            "arima_bic": arima_bic,
            "arima_residual_std": float(np.std(residuals)),
        }

        if mlflow_run:
            try:
                import mlflow
                mlflow.log_metrics({
                    "arima_aic": arima_aic,
                    "arima_bic": arima_bic,
                })
                mlflow.log_params({"arima_order": str(self._arima_order)})
            except Exception:
                pass

        logger.info("ARIMA+GARCH eğitimi tamamlandı.", **metrics)
        return metrics

    def forecast(
        self,
        steps: int = 1,
        current_price: float = None,
    ) -> Dict:
        """
        h-adım ilerisini tahmin eder.

        Returns:
            {
              'point_forecast': float,   # Tahmin edilen log-return
              'price_forecast': float,   # Tahmin edilen fiyat
              'volatility': float,       # Tahmini volatilite
              'lower_95': float,
              'upper_95': float,
            }
        """
        if self.arima_fitted is None:
            raise RuntimeError("Model henüz eğitilmedi.")

        # ARIMA tahmini
        arima_forecast = self.arima_fitted.forecast(steps=steps)
        predicted_log_return = float(arima_forecast.iloc[-1]) / 100

        # GARCH volatilite tahmini
        if self.garch_fitted:
            try:
                garch_forecast = self.garch_fitted.forecast(horizon=steps, reindex=False)
                variance = float(garch_forecast.variance.iloc[-1, -1])
                vol = float(np.sqrt(variance)) / 100
            except Exception:
                vol = 0.02  # varsayılan %2 günlük volatilite
        else:
            vol = 0.02

        # %95 güven aralığı (1.96 sigma)
        lower = predicted_log_return - 1.96 * vol * np.sqrt(steps)
        upper = predicted_log_return + 1.96 * vol * np.sqrt(steps)

        result = {
            "predicted_log_return": predicted_log_return,
            "volatility_daily": vol,
            "lower_95": lower,
            "upper_95": upper,
        }

        if current_price:
            result["price_forecast"] = current_price * np.exp(predicted_log_return * steps)
            result["price_lower"] = current_price * np.exp(lower)
            result["price_upper"] = current_price * np.exp(upper)

        return result

    def _select_arima_order(self, series: np.ndarray) -> Tuple[int, int, int]:
        """
        AIC kriteriyle en iyi ARIMA(p,d,q) parametrelerini seçer.
        Aday uzayı: p ∈ {0,1,2}, d ∈ {0,1}, q ∈ {0,1,2}
        """
        try:
            from statsmodels.tsa.statespace.sarimax import SARIMAX
        except ImportError:
            return (1, 1, 1)  # varsayılan

        best_aic = np.inf
        best_order = (1, 1, 1)

        for p in range(3):
            for d in range(2):
                for q in range(3):
                    if p + q == 0:
                        continue
                    try:
                        model = SARIMAX(
                            series, order=(p, d, q),
                            enforce_stationarity=False,
                            enforce_invertibility=False,
                        )
                        result = model.fit(disp=False, maxiter=100)
                        if result.aic < best_aic:
                            best_aic = result.aic
                            best_order = (p, d, q)
                    except Exception:
                        continue

        logger.debug("ARIMA order seçildi.", order=best_order, aic=best_aic)
        return best_order

    def save(self, ticker: str, timeframe: str) -> str:
        """ARIMA+GARCH modellerini kaydeder."""
        path = os.path.join(
            settings.MODEL_ARTIFACTS_PATH,
            "arima_garch",
            ticker,
            f"{timeframe}.pkl",
        )
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({
                "arima_fitted": self.arima_fitted,
                "garch_fitted": self.garch_fitted,
                "arima_order": self._arima_order,
            }, f)
        logger.info("ARIMA+GARCH modeli kaydedildi.", path=path)
        return path

    def load(self, ticker: str, timeframe: str) -> bool:
        """Kaydedilmiş modeli yükler."""
        try:
            path = os.path.join(
                settings.MODEL_ARTIFACTS_PATH,
                "arima_garch",
                ticker,
                f"{timeframe}.pkl",
            )
            if not os.path.exists(path):
                return False
            with open(path, "rb") as f:
                data = pickle.load(f)
            self.arima_fitted = data["arima_fitted"]
            self.garch_fitted = data["garch_fitted"]
            self._arima_order = data["arima_order"]
            logger.info("ARIMA+GARCH modeli yüklendi.", ticker=ticker, timeframe=timeframe)
            return True
        except Exception as e:
            logger.warning("ARIMA+GARCH model yükleme hatası.", error=str(e))
            return False

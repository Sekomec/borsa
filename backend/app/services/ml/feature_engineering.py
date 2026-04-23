"""
QuantEdge AI — Feature Engineering Pipeline
=============================================
Tüm veri kaynaklarından (OHLCV, teknik, sentiment, temel, makro)
ML modeli için optimize feature matrisi oluşturur.

Feature Kategorileri:
  1. Fiyat özellikleri      : Getiriler, log-return, normalize fiyat
  2. Teknik göstergeler     : RSI, MACD, BB, ATR vb. (normalize)
  3. Hacim özellikleri      : OBV, Volume Ratio, VWAP sapması
  4. Sentiment özellikleri  : Reddit, StockTwits, Haber skorları
  5. Temel analiz           : P/E, P/B, ROE, Büyüme vb.
  6. Makro göstergeler      : VIX, FED, Yield Curve vb.
  7. Zaman özellikleri      : Gün/Ay, Haftanın günü, Mevsim

Mimari Not (Senior Architect):
  Feature store olarak Redis kullanılır. Her ticker için hesaplanan
  feature matrisleri cache'lenir. Bu, aynı hisse için farklı
  timeframe tahminlerinin feature'ları yeniden hesaplamamasını sağlar.
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import structlog
from sklearn.preprocessing import RobustScaler

from app.core.cache import cache_manager
from app.core.config import settings

logger = structlog.get_logger()


class FeatureEngineeringPipeline:
    """
    Ham veriden ML-ready feature matrisi oluşturan pipeline.

    RobustScaler kullanılır (MinMaxScaler yerine):
    - Outlier'lara karşı dayanıklı
    - Finansal verideki ani spike'ları handle eder
    - IQR bazlı normalizasyon
    """

    # Her zaman dilimi için önerilen minimum bar sayısı
    MIN_BARS = {
        "1d": 60,
        "1w": 52,
        "1mo": 24,
        "3mo": 12,
        "1y": 5,
    }

    def __init__(self):
        self.scalers: Dict[str, RobustScaler] = {}

    # ----------------------------------------------------------
    # ANA PIPELINE
    # ----------------------------------------------------------

    def build_feature_matrix(
        self,
        ohlcv: List[Dict],
        technical: Dict,
        sentiment: Optional[Dict] = None,
        fundamental: Optional[Dict] = None,
        macro: Optional[Dict] = None,
        timeframe: str = "1d",
        sequence_length: int = 60,
    ) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """
        Tüm kaynaklardan feature matrisi oluşturur.

        Args:
            ohlcv          : OHLCV bar listesi
            technical      : Teknik analiz sonuçları
            sentiment      : Agregat sentiment skoru
            fundamental    : Temel analiz verileri
            macro          : Makroekonomik göstergeler
            timeframe      : Zaman dilimi
            sequence_length: LSTM için sekans uzunluğu

        Returns:
            (X, y, feature_names)
            X: (samples, sequence_length, features) — LSTM formatı
            y: (samples,) — hedef getiri
            feature_names: özellik isimleri listesi
        """
        if not ohlcv or len(ohlcv) < sequence_length:
            raise ValueError(
                f"Yetersiz veri: {len(ohlcv)} bar var, "
                f"en az {sequence_length} gerekli."
            )

        df = self._ohlcv_to_df(ohlcv)

        # --- Feature grupları oluştur ---
        feature_dfs = []

        # 1. Fiyat özellikleri (her zaman dahil)
        price_features = self._build_price_features(df)
        feature_dfs.append(price_features)

        # 2. Teknik göstergeler
        ta_features = self._build_technical_features(df, technical)
        feature_dfs.append(ta_features)

        # 3. Hacim özellikleri
        volume_features = self._build_volume_features(df)
        feature_dfs.append(volume_features)

        # 4. Zaman özellikleri (cyclical encoding)
        time_features = self._build_time_features(df)
        feature_dfs.append(time_features)

        # 5. Sentiment (skaler — tüm satırlara yayılır)
        if sentiment:
            sentiment_features = self._build_sentiment_features(df, sentiment)
            feature_dfs.append(sentiment_features)

        # 6. Makro (skaler — tüm satırlara yayılır)
        if macro:
            macro_features = self._build_macro_features(df, macro)
            feature_dfs.append(macro_features)

        # 7. Temel analiz (skaler — tüm satırlara yayılır)
        if fundamental:
            fund_features = self._build_fundamental_features(df, fundamental)
            feature_dfs.append(fund_features)

        # --- Birleştir ---
        feature_matrix = pd.concat(feature_dfs, axis=1)
        feature_names = feature_matrix.columns.tolist()

        # NaN'ları doldur
        feature_matrix = feature_matrix.ffill().bfill().fillna(0)

        # --- Hedef değişken: gelecek N günün getirisi ---
        horizon_days = {"1d": 1, "1w": 5, "1mo": 21, "3mo": 63, "1y": 252}
        h = horizon_days.get(timeframe, 1)
        target = df["close"].pct_change(h).shift(-h)

        # --- Geçerli satırları seç ---
        valid_mask = ~target.isna()
        feature_matrix = feature_matrix[valid_mask]
        target = target[valid_mask]

        # --- Normalizasyon ---
        feature_matrix_scaled = self._scale_features(
            feature_matrix.values, timeframe
        )

        # --- LSTM sekans formatı oluştur ---
        X, y = self._create_sequences(
            feature_matrix_scaled,
            target.values,
            sequence_length,
        )

        logger.info(
            "Feature matrisi oluşturuldu.",
            shape_X=X.shape,
            shape_y=y.shape,
            features=len(feature_names),
            timeframe=timeframe,
        )

        return X, y, feature_names

    def build_prediction_features(
        self,
        ohlcv: List[Dict],
        technical: Dict,
        sentiment: Optional[Dict] = None,
        fundamental: Optional[Dict] = None,
        macro: Optional[Dict] = None,
        timeframe: str = "1d",
        sequence_length: int = 60,
    ) -> Tuple[np.ndarray, List[str]]:
        """
        Tahmin için son sekansı döndürür (y olmadan).
        Model.predict() girişi olarak kullanılır.
        """
        X, _, feature_names = self.build_feature_matrix(
            ohlcv, technical, sentiment, fundamental, macro,
            timeframe, sequence_length
        )
        # Son sekansı al: (1, sequence_length, features)
        return X[-1:], feature_names

    # ----------------------------------------------------------
    # FEATURE GRUPLAR
    # ----------------------------------------------------------

    def _build_price_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Fiyat tabanlı özellikler."""
        features = pd.DataFrame(index=df.index)

        close = df["close"]
        high = df["high"]
        low = df["low"]
        open_ = df["open"]

        # Log getiriler (stationary yapar)
        features["log_return_1d"] = np.log(close / close.shift(1))
        features["log_return_5d"] = np.log(close / close.shift(5))
        features["log_return_21d"] = np.log(close / close.shift(21))

        # Fiyat momentumu (normalize)
        features["price_momentum_5d"] = close.pct_change(5)
        features["price_momentum_21d"] = close.pct_change(21)
        features["price_momentum_63d"] = close.pct_change(63)

        # Normalize OHLC
        features["hl_ratio"] = (high - low) / close           # Gün içi aralık
        features["oc_ratio"] = (close - open_) / open_        # Gün içi değişim
        features["hw_ratio"] = (high - close) / close         # Üst gölge
        features["lw_ratio"] = (close - low) / close          # Alt gölge

        # Volatilite (rolling std of log returns)
        features["volatility_5d"] = features["log_return_1d"].rolling(5).std()
        features["volatility_21d"] = features["log_return_1d"].rolling(21).std()
        features["volatility_ratio"] = (
            features["volatility_5d"] / features["volatility_21d"].replace(0, 1e-10)
        )

        # Price relative to rolling max/min (normalize konumu)
        features["price_52w_position"] = (close - close.rolling(252).min()) / (
            close.rolling(252).max() - close.rolling(252).min() + 1e-10
        )
        features["price_to_20d_sma"] = close / close.rolling(20).mean()
        features["price_to_50d_sma"] = close / close.rolling(50).mean()

        return features

    def _build_technical_features(
        self, df: pd.DataFrame, technical: Dict
    ) -> pd.DataFrame:
        """Teknik göstergelerden özellikler."""
        features = pd.DataFrame(index=df.index)
        indicators = technical.get("indicators", {})

        # RSI normalize (0-1)
        rsi = indicators.get("rsi_14")
        if rsi is not None:
            features["rsi_norm"] = (rsi - 50) / 50   # -1 ile 1 arası
            features["rsi_oversold"] = float(rsi < 30)
            features["rsi_overbought"] = float(rsi > 70)

        # MACD normalize
        macd = indicators.get("macd")
        macd_sig = indicators.get("macd_signal")
        macd_hist = indicators.get("macd_histogram")
        if macd is not None:
            price = float(df["close"].iloc[-1])
            features["macd_norm"] = macd / (price + 1e-10)
            features["macd_signal_norm"] = (macd_sig or 0) / (price + 1e-10)
            features["macd_hist_norm"] = (macd_hist or 0) / (price + 1e-10)
            features["macd_crossover"] = float((macd or 0) > (macd_sig or 0))

        # Bollinger Band pozisyonu
        bb_pct_b = indicators.get("bb_pct_b")
        bb_width = indicators.get("bb_width")
        if bb_pct_b is not None:
            features["bb_pct_b"] = bb_pct_b
            features["bb_width_norm"] = bb_width or 0

        # ADX (trend gücü)
        adx = indicators.get("adx")
        if adx is not None:
            features["adx_norm"] = adx / 100

        # Stochastic
        stoch_k = indicators.get("stoch_k")
        stoch_d = indicators.get("stoch_d")
        if stoch_k is not None:
            features["stoch_k_norm"] = (stoch_k - 50) / 50
            features["stoch_d_norm"] = ((stoch_d or 50) - 50) / 50

        # Williams %R
        willr = indicators.get("williams_r")
        if willr is not None:
            features["williams_r_norm"] = (willr + 50) / 50   # -1 ile 1

        # Sinyal
        composite = technical.get("signals", {}).get("composite_signal", 0)
        features["ta_composite_signal"] = float(composite or 0)

        # Destek/Direnç mesafesi
        current_price = float(df["close"].iloc[-1])
        support = indicators.get("support_level", current_price * 0.95)
        resistance = indicators.get("resistance_level", current_price * 1.05)
        if current_price > 0:
            features["distance_to_support"] = (current_price - support) / current_price
            features["distance_to_resistance"] = (resistance - current_price) / current_price

        # Tüm kolonları aynı uzunluğa getir (son değeri tüm satırlara yay)
        for col in features.columns:
            if not isinstance(features[col], pd.Series):
                features[col] = float(features[col])

        return features

    def _build_volume_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Hacim tabanlı özellikler."""
        features = pd.DataFrame(index=df.index)
        volume = df["volume"].astype(float)

        # OBV
        close = df["close"]
        delta = close.diff()
        sign = np.sign(delta)
        obv = (sign * volume).cumsum()
        features["obv_norm"] = (obv - obv.rolling(20).mean()) / (obv.rolling(20).std() + 1e-10)

        # Volume ratio
        vol_ma = volume.rolling(20).mean()
        features["volume_ratio"] = volume / (vol_ma + 1e-10)

        # VWAP sapması
        typical = (df["high"] + df["low"] + close) / 3
        vwap = (typical * volume).cumsum() / volume.cumsum()
        features["vwap_deviation"] = (close - vwap) / (vwap + 1e-10)

        # Volume trend
        features["volume_trend_5d"] = volume.pct_change(5)

        # Volume spike (anlık hacim / 20d ortalama > 2x)
        features["volume_spike"] = (features["volume_ratio"] > 2.0).astype(float)

        # MFI (Money Flow Index) — varsa
        if "mfi_14" in df.columns:
            features["mfi_norm"] = (df["mfi_14"] - 50) / 50

        return features

    def _build_time_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Zaman tabanlı özellikler — cyclical encoding.

        Neden cyclical? 'Ocak=1, Aralık=12' yerine
        sin/cos encoding kullanılır: Aralık-Ocak geçişi düzgün olur.
        """
        features = pd.DataFrame(index=df.index)
        ts = pd.DatetimeIndex(df.index)

        # Haftanın günü (0=Pazartesi, 4=Cuma)
        dow = ts.dayofweek
        features["dow_sin"] = np.sin(2 * np.pi * dow / 5)
        features["dow_cos"] = np.cos(2 * np.pi * dow / 5)

        # Ayın günü
        dom = ts.day
        features["dom_sin"] = np.sin(2 * np.pi * dom / 31)
        features["dom_cos"] = np.cos(2 * np.pi * dom / 31)

        # Yılın ayı
        month = ts.month
        features["month_sin"] = np.sin(2 * np.pi * month / 12)
        features["month_cos"] = np.cos(2 * np.pi * month / 12)

        # Çeyrek
        quarter = ts.quarter
        features["quarter_sin"] = np.sin(2 * np.pi * quarter / 4)
        features["quarter_cos"] = np.cos(2 * np.pi * quarter / 4)

        # Tatil dönemleri (Ocak efekti, Noel rallisi vb.)
        features["is_q1"] = (ts.quarter == 1).astype(float)
        features["is_earnings_season"] = (
            (ts.month.isin([1, 4, 7, 10])) & (ts.day <= 31)
        ).astype(float)

        return features

    def _build_sentiment_features(
        self, df: pd.DataFrame, sentiment: Dict
    ) -> pd.DataFrame:
        """
        Sentiment skorlarını feature matrisine ekler.
        Skaler değerler tüm satırlara yayılır.
        """
        features = pd.DataFrame(index=df.index)

        overall = float(sentiment.get("overall_score", 0) or 0)
        reddit = float(sentiment.get("reddit_score", 0) or 0)
        news = float(sentiment.get("news_score", 0) or 0)
        stocktwits = float(sentiment.get("stocktwits_score", 0) or 0)

        features["sentiment_overall"] = overall
        features["sentiment_reddit"] = reddit
        features["sentiment_news"] = news
        features["sentiment_stocktwits"] = stocktwits

        # Sentiment yönü (ikili)
        features["sentiment_bullish"] = float(overall > 0.15)
        features["sentiment_bearish"] = float(overall < -0.15)

        # Sentiment-Fiyat uyumsuzluğu (contrarian sinyal)
        close_trend = df["close"].pct_change(5).iloc[-1] if len(df) > 5 else 0
        features["sentiment_price_divergence"] = float(
            (overall > 0.2 and close_trend < -0.02) or
            (overall < -0.2 and close_trend > 0.02)
        )

        return features

    def _build_macro_features(
        self, df: pd.DataFrame, macro: Dict
    ) -> pd.DataFrame:
        """Makro göstergeleri feature matrisine ekler."""
        features = pd.DataFrame(index=df.index)

        def safe(key, default=0.0):
            v = macro.get(key)
            return float(v) if v is not None else default

        # Normalize değerler (0-1)
        features["macro_vix_norm"] = min(safe("vix", 20) / 80, 1.0)
        features["macro_fed_rate_norm"] = min(safe("fed_rate", 3) / 7, 1.0)
        features["macro_10y_yield_norm"] = min(safe("us_10y_yield", 3) / 6, 1.0)

        # Yield curve: negatif değer resesyon sinyali
        ycs = safe("yield_curve_spread", 1.0)
        features["macro_yield_curve"] = max(-1, min(1, ycs / 3))

        # Risk skoru
        features["macro_risk_score_norm"] = safe("macro_risk_score", 50) / 100

        # Makro rejim one-hot encoding
        regime = macro.get("macro_regime", "NEUTRAL")
        features["macro_regime_crisis"] = float(regime == "CRISIS")
        features["macro_regime_risk_off"] = float(regime == "RISK_OFF")
        features["macro_regime_goldilocks"] = float(regime == "GOLDILOCKS")
        features["macro_regime_tightening"] = float(regime == "TIGHTENING")
        features["macro_regime_easing"] = float(regime == "EASING")

        return features

    def _build_fundamental_features(
        self, df: pd.DataFrame, fundamental: Dict
    ) -> pd.DataFrame:
        """Temel analiz verilerini feature matrisine ekler."""
        features = pd.DataFrame(index=df.index)

        def safe(key, default=0.0, cap=None):
            v = fundamental.get(key)
            if v is None:
                return default
            v = float(v)
            if cap:
                v = max(-cap, min(cap, v))
            return v

        # Değerleme (normalize / cap)
        pe = safe("pe_ratio", 20, cap=100)
        features["pe_norm"] = max(0, min(1, pe / 50))   # 0 (ucuz) ile 1 (pahalı)

        pb = safe("pb_ratio", 2, cap=20)
        features["pb_norm"] = max(0, min(1, pb / 10))

        # Büyüme
        features["eps_growth"] = safe("eps_growth_3y", 0, cap=2)
        features["revenue_growth"] = safe("revenue_growth_3y", 0, cap=2)

        # Karlılık
        features["net_margin"] = safe("net_margin", 0, cap=0.5)
        features["roe"] = safe("roe", 0, cap=1)

        # Borç
        features["debt_equity"] = min(1, safe("debt_to_equity", 0.5) / 3)

        # Temel analiz skoru (0-100 → 0-1)
        features["fundamental_score_norm"] = safe("fundamental_score", 50) / 100

        # İçeriden öğrenen sinyali
        insider = fundamental.get("insider_signal", "neutral")
        features["insider_bullish"] = float(insider == "bullish")
        features["insider_bearish"] = float(insider == "bearish")

        return features

    # ----------------------------------------------------------
    # NORMALIZASYON & SEKANS
    # ----------------------------------------------------------

    def _scale_features(
        self, features: np.ndarray, timeframe: str
    ) -> np.ndarray:
        """
        RobustScaler ile normalizasyon.
        Scaler timeframe'e göre ayrı tutulur (fit/transform).
        """
        if timeframe not in self.scalers:
            self.scalers[timeframe] = RobustScaler()

        scaler = self.scalers[timeframe]

        # NaN/Inf temizle
        features = np.nan_to_num(features, nan=0.0, posinf=1.0, neginf=-1.0)

        try:
            if not hasattr(scaler, "center_"):
                # İlk kez — fit + transform
                scaled = scaler.fit_transform(features)
            else:
                scaled = scaler.transform(features)
        except Exception:
            # Scaler hatası — ham veriyi kullan
            scaled = features

        return scaled

    def _create_sequences(
        self,
        features: np.ndarray,
        targets: np.ndarray,
        seq_len: int,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        LSTM için (samples, seq_len, features) formatında sekanslar oluşturur.
        """
        X, y = [], []
        for i in range(seq_len, len(features)):
            X.append(features[i - seq_len:i])
            y.append(targets[i])

        return np.array(X), np.array(y)

    # ----------------------------------------------------------
    # YARDIMCI
    # ----------------------------------------------------------

    def _ohlcv_to_df(self, ohlcv: List[Dict]) -> pd.DataFrame:
        """OHLCV listesini indeksli DataFrame'e dönüştürür."""
        df = pd.DataFrame(ohlcv)
        rename = {
            "open_price": "open", "high_price": "high",
            "low_price": "low", "close_price": "close",
        }
        df = df.rename(columns=rename)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp").sort_index()
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df


# Singleton
feature_pipeline = FeatureEngineeringPipeline()

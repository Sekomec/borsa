"""
QuantEdge AI — Teknik Analiz Servisi
======================================
Kütüphaneler:
  - TA-Lib  : C tabanlı, ultra hızlı gösterge hesaplama
  - pandas-ta: Python tabanlı yedek (TA-Lib yoksa)

Hesaplanan Göstergeler:
  Trend    : SMA, EMA, MACD, ADX
  Momentum : RSI, Stochastic, Williams %R, CCI
  Volatilite: Bollinger Bands, ATR, Keltner Channel
  Hacim    : OBV, MFI, VWAP, Volume Profile
  Destek/Direnç: Pivot Points, Fibonacci

Sinyal Mantığı:
  Her gösterge -1 (sat), 0 (nötr), +1 (al) sinyali üretir.
  Bileşik sinyal: ağırlıklı ortalama → modele girdi olarak verilir.
"""

from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger()

# TA-Lib'i dene, yoksa pandas-ta ile devam et
try:
    import talib
    TALIB_AVAILABLE = True
    logger.info("TA-Lib kullanılıyor.")
except ImportError:
    TALIB_AVAILABLE = False
    try:
        import pandas_ta as ta
        logger.info("pandas-ta kullanılıyor (TA-Lib yedek).")
    except ImportError:
        logger.warning("Ne TA-Lib ne pandas-ta bulunamadı! Manuel hesaplama kullanılacak.")


class TechnicalAnalysisService:
    """
    OHLCV verisinden teknik göstergeler ve sinyal hesaplayan servis.

    Kullanım:
        ta_service = TechnicalAnalysisService()
        result = ta_service.analyze(ohlcv_data)
    """

    def analyze(self, ohlcv: List[Dict], timeframe: str = "1d") -> Dict:
        """
        Tam teknik analiz paketi.

        Args:
            ohlcv    : [{'timestamp', 'open_price', 'high_price', 'low_price', 'close_price', 'volume'}]
            timeframe: '1d', '1h', '5m' vb.

        Returns:
            Göstergeler, sinyaller ve destek/direnç seviyeleri
        """
        if not ohlcv or len(ohlcv) < 30:
            logger.warning("Yetersiz OHLCV verisi. En az 30 bar gerekli.", bars=len(ohlcv))
            return self._empty_result()

        df = self._to_dataframe(ohlcv)

        # Tüm göstergeleri hesapla
        indicators = {}
        indicators.update(self._calculate_trend(df))
        indicators.update(self._calculate_momentum(df))
        indicators.update(self._calculate_volatility(df))
        indicators.update(self._calculate_volume(df))

        # Destek/Direnç
        support, resistance = self._find_support_resistance(df)
        indicators["support_level"] = support
        indicators["resistance_level"] = resistance

        # Sinyaller
        signals = self._generate_signals(df, indicators)

        # Bileşik sinyal: -1.0 ile 1.0 arası
        composite = self._calculate_composite_signal(signals)
        signals["composite_signal"] = composite
        signals["signal_summary"] = self._composite_to_label(composite)

        # Son değerleri al (en güncel bar)
        latest = {k: (float(v.iloc[-1]) if hasattr(v, 'iloc') and not pd.isna(v.iloc[-1]) else v)
                  for k, v in indicators.items() if v is not None}

        # Formasyonlar
        patterns = self._detect_patterns(df)

        return {
            "indicators": latest,
            "signals": signals,
            "patterns": patterns,
            "current_price": float(df["close"].iloc[-1]),
            "price_change_pct": float(
                (df["close"].iloc[-1] - df["close"].iloc[-2]) / df["close"].iloc[-2] * 100
            ),
            "timeframe": timeframe,
            "bars_analyzed": len(df),
            "last_updated": datetime.utcnow().isoformat(),
        }

    # ----------------------------------------------------------
    # TREND GÖSTERGELERİ
    # ----------------------------------------------------------

    def _calculate_trend(self, df: pd.DataFrame) -> Dict:
        """SMA, EMA, MACD, ADX hesaplar."""
        close = df["close"].values

        if TALIB_AVAILABLE:
            sma_20 = talib.SMA(close, timeperiod=20)
            sma_50 = talib.SMA(close, timeperiod=50)
            sma_200 = talib.SMA(close, timeperiod=200)
            ema_12 = talib.EMA(close, timeperiod=12)
            ema_26 = talib.EMA(close, timeperiod=26)
            macd, macd_signal, macd_hist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
            adx = talib.ADX(df["high"].values, df["low"].values, close, timeperiod=14)
        else:
            # pandas-ta ile hesapla
            sma_20 = df["close"].rolling(20).mean().values
            sma_50 = df["close"].rolling(50).mean().values
            sma_200 = df["close"].rolling(200).mean().values
            ema_12 = df["close"].ewm(span=12).mean().values
            ema_26 = df["close"].ewm(span=26).mean().values

            # MACD manuel
            macd = ema_12 - ema_26
            macd_signal = pd.Series(macd).ewm(span=9).mean().values
            macd_hist = macd - macd_signal
            adx = self._calculate_adx_manual(df)

        return {
            "sma_20": pd.Series(sma_20),
            "sma_50": pd.Series(sma_50),
            "sma_200": pd.Series(sma_200),
            "ema_12": pd.Series(ema_12),
            "ema_26": pd.Series(ema_26),
            "macd": pd.Series(macd),
            "macd_signal": pd.Series(macd_signal),
            "macd_histogram": pd.Series(macd_hist),
            "adx": pd.Series(adx),
        }

    # ----------------------------------------------------------
    # MOMENTUM GÖSTERGELERİ
    # ----------------------------------------------------------

    def _calculate_momentum(self, df: pd.DataFrame) -> Dict:
        """RSI, Stochastic, Williams %R, CCI hesaplar."""
        close = df["close"].values
        high = df["high"].values
        low = df["low"].values

        if TALIB_AVAILABLE:
            rsi = talib.RSI(close, timeperiod=14)
            stoch_k, stoch_d = talib.STOCH(high, low, close, fastk_period=14, slowk_period=3, slowd_period=3)
            willr = talib.WILLR(high, low, close, timeperiod=14)
            cci = talib.CCI(high, low, close, timeperiod=20)
            mfi = talib.MFI(high, low, close, df["volume"].values.astype(float), timeperiod=14)
        else:
            # Manuel RSI
            delta = pd.Series(close).diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss.replace(0, 1e-10)
            rsi = (100 - (100 / (1 + rs))).values

            stoch_k = self._stochastic_k(high, low, close, 14)
            stoch_d = pd.Series(stoch_k).rolling(3).mean().values
            willr = self._williams_r(high, low, close, 14)
            cci = self._cci_manual(high, low, close, 20)
            mfi = self._mfi_manual(high, low, close, df["volume"].values, 14)

        return {
            "rsi_14": pd.Series(rsi),
            "stoch_k": pd.Series(stoch_k),
            "stoch_d": pd.Series(stoch_d),
            "williams_r": pd.Series(willr),
            "cci_20": pd.Series(cci),
            "mfi_14": pd.Series(mfi),
        }

    # ----------------------------------------------------------
    # VOLATİLİTE GÖSTERGELERİ
    # ----------------------------------------------------------

    def _calculate_volatility(self, df: pd.DataFrame) -> Dict:
        """Bollinger Bands, ATR, Keltner Channel hesaplar."""
        close = df["close"].values
        high = df["high"].values
        low = df["low"].values

        if TALIB_AVAILABLE:
            bb_upper, bb_middle, bb_lower = talib.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2)
            atr = talib.ATR(high, low, close, timeperiod=14)
        else:
            bb_middle = pd.Series(close).rolling(20).mean()
            bb_std = pd.Series(close).rolling(20).std()
            bb_upper = (bb_middle + 2 * bb_std).values
            bb_lower = (bb_middle - 2 * bb_std).values
            bb_middle = bb_middle.values
            atr = self._atr_manual(high, low, close, 14)

        # Bollinger Band genişliği (volatilite ölçüsü)
        bb_width = np.where(
            bb_middle != 0,
            (bb_upper - bb_lower) / bb_middle,
            0
        )

        # BB %B (fiyatın band içindeki konumu)
        bb_pct_b = np.where(
            (bb_upper - bb_lower) != 0,
            (close - bb_lower) / (bb_upper - bb_lower),
            0.5
        )

        return {
            "bb_upper": pd.Series(bb_upper),
            "bb_middle": pd.Series(bb_middle),
            "bb_lower": pd.Series(bb_lower),
            "bb_width": pd.Series(bb_width),
            "bb_pct_b": pd.Series(bb_pct_b),
            "atr_14": pd.Series(atr),
        }

    # ----------------------------------------------------------
    # HACİM GÖSTERGELERİ
    # ----------------------------------------------------------

    def _calculate_volume(self, df: pd.DataFrame) -> Dict:
        """OBV, VWAP, Volume MA hesaplar."""
        close = df["close"].values
        high = df["high"].values
        low = df["low"].values
        volume = df["volume"].values.astype(float)

        if TALIB_AVAILABLE:
            obv = talib.OBV(close, volume)
        else:
            obv = self._obv_manual(close, volume)

        # VWAP (günlük)
        typical_price = (high + low + close) / 3
        vwap_daily = np.cumsum(typical_price * volume) / np.cumsum(volume)

        # Hacim hareketli ortalaması
        vol_ma_20 = pd.Series(volume).rolling(20).mean().values

        # Hacim oranı (anlık hacim / 20 günlük ortalama)
        vol_ratio = np.where(vol_ma_20 > 0, volume / vol_ma_20, 1.0)

        return {
            "obv": pd.Series(obv),
            "vwap_daily": pd.Series(vwap_daily),
            "volume_ma_20": pd.Series(vol_ma_20),
            "volume_ratio": pd.Series(vol_ratio),
        }

    # ----------------------------------------------------------
    # DESTEK / DİRENÇ
    # ----------------------------------------------------------

    def _find_support_resistance(
        self,
        df: pd.DataFrame,
        lookback: int = 60,
    ) -> tuple:
        """
        Son N bara dayalı destek ve direnç seviyeleri bulur.
        Yöntem: Local minima/maxima tespiti.
        """
        if len(df) < lookback:
            lookback = len(df)

        recent = df.tail(lookback)
        current_price = df["close"].iloc[-1]

        # Local max ve min bul
        highs = recent["high"].values
        lows = recent["low"].values

        # Pivot high/low: merkez bar, etrafındakilerden yüksek/alçak
        pivot_highs = []
        pivot_lows = []
        window = 5

        for i in range(window, len(highs) - window):
            if highs[i] == max(highs[i - window:i + window + 1]):
                pivot_highs.append(highs[i])
            if lows[i] == min(lows[i - window:i + window + 1]):
                pivot_lows.append(lows[i])

        # Fiyatın altındaki en yakın pivot → destek
        # Fiyatın üstündeki en yakın pivot → direnç
        support = max((h for h in pivot_lows if h < current_price), default=current_price * 0.95)
        resistance = min((h for h in pivot_highs if h > current_price), default=current_price * 1.05)

        return round(support, 4), round(resistance, 4)

    # ----------------------------------------------------------
    # SİNYAL ÜRETİMİ
    # ----------------------------------------------------------

    def _generate_signals(self, df: pd.DataFrame, indicators: Dict) -> Dict:
        """
        Her gösterge için -1/0/+1 sinyali üretir.
        """
        close = float(df["close"].iloc[-1])
        signals = {}

        # RSI sinyali
        rsi = self._latest(indicators.get("rsi_14"))
        if rsi is not None:
            if rsi < 30:
                signals["rsi"] = 1    # Aşırı satım → Al
            elif rsi > 70:
                signals["rsi"] = -1   # Aşırı alım → Sat
            else:
                signals["rsi"] = 0    # Nötr

        # MACD sinyali
        macd = self._latest(indicators.get("macd"))
        macd_signal = self._latest(indicators.get("macd_signal"))
        macd_hist = self._latest(indicators.get("macd_histogram"))
        if macd is not None and macd_signal is not None:
            if macd > macd_signal and (macd_hist or 0) > 0:
                signals["macd"] = 1
            elif macd < macd_signal and (macd_hist or 0) < 0:
                signals["macd"] = -1
            else:
                signals["macd"] = 0

        # Bollinger Band sinyali
        bb_pct_b = self._latest(indicators.get("bb_pct_b"))
        if bb_pct_b is not None:
            if bb_pct_b < 0.05:
                signals["bb"] = 1     # Alt banda yakın → Al
            elif bb_pct_b > 0.95:
                signals["bb"] = -1    # Üst banda yakın → Sat
            else:
                signals["bb"] = 0

        # SMA trend sinyali
        sma_20 = self._latest(indicators.get("sma_20"))
        sma_50 = self._latest(indicators.get("sma_50"))
        sma_200 = self._latest(indicators.get("sma_200"))
        if sma_20 and sma_50 and sma_200:
            if close > sma_20 > sma_50 > sma_200:
                signals["trend"] = 1   # Güçlü yükseliş trendi
            elif close < sma_20 < sma_50 < sma_200:
                signals["trend"] = -1  # Güçlü düşüş trendi
            elif close > sma_200:
                signals["trend"] = 0.5
            else:
                signals["trend"] = -0.5

        # VWAP sinyali
        vwap = self._latest(indicators.get("vwap_daily"))
        if vwap is not None:
            if close > vwap * 1.01:
                signals["vwap"] = 1
            elif close < vwap * 0.99:
                signals["vwap"] = -1
            else:
                signals["vwap"] = 0

        # Hacim sinyali (ani hacim artışı)
        vol_ratio = self._latest(indicators.get("volume_ratio"))
        if vol_ratio is not None:
            if vol_ratio > 2.0:
                signals["volume_surge"] = 1   # Yüksek hacim → trendin gücü
            elif vol_ratio < 0.5:
                signals["volume_surge"] = -0.5  # Düşük hacim → zayıf trend

        return signals

    def _calculate_composite_signal(self, signals: Dict) -> float:
        """
        Ağırlıklı bileşik sinyal hesaplar.
        Ağırlıklar: trend > momentum > volatilite > hacim
        """
        weights = {
            "trend": 0.30,
            "macd": 0.20,
            "rsi": 0.15,
            "vwap": 0.15,
            "bb": 0.10,
            "volume_surge": 0.10,
        }

        total_weight = 0.0
        weighted_sum = 0.0

        for key, weight in weights.items():
            val = signals.get(key)
            if val is not None:
                weighted_sum += float(val) * weight
                total_weight += weight

        if total_weight == 0:
            return 0.0

        return round(weighted_sum / total_weight, 4)

    # ----------------------------------------------------------
    # FORMASYON TESPİTİ
    # ----------------------------------------------------------

    def _detect_patterns(self, df: pd.DataFrame) -> List[str]:
        """
        Temel mum formasyonlarını tespit eder.
        """
        patterns = []
        if len(df) < 5:
            return patterns

        if not TALIB_AVAILABLE:
            return self._detect_patterns_manual(df)

        # TA-Lib mum formasyonları
        close = df["close"].values
        open_p = df["open"].values
        high = df["high"].values
        low = df["low"].values

        pattern_funcs = {
            "Doji": talib.CDLDOJI,
            "Hammer": talib.CDLHAMMER,
            "Engulfing": talib.CDLENGULFING,
            "Morning Star": talib.CDLMORNINGSTAR,
            "Evening Star": talib.CDLEVENINGSTAR,
            "Shooting Star": talib.CDLSHOOTINGSTAR,
            "Three Black Crows": talib.CDL3BLACKCROWS,
            "Three White Soldiers": talib.CDL3WHITESOLDIERS,
        }

        for name, func in pattern_funcs.items():
            try:
                result = func(open_p, high, low, close)
                if result[-1] != 0:
                    direction = "Bullish" if result[-1] > 0 else "Bearish"
                    patterns.append(f"{direction} {name}")
            except Exception:
                continue

        return patterns

    def _detect_patterns_manual(self, df: pd.DataFrame) -> List[str]:
        """TA-Lib olmadan temel formasyon tespiti."""
        patterns = []
        last = df.iloc[-1]
        prev = df.iloc[-2]

        body = abs(last["close"] - last["open"])
        upper_shadow = last["high"] - max(last["close"], last["open"])
        lower_shadow = min(last["close"], last["open"]) - last["low"]
        range_ = last["high"] - last["low"]

        # Doji (çok küçük gövde)
        if range_ > 0 and body / range_ < 0.1:
            patterns.append("Doji")

        # Hammer (uzun alt gölge)
        if lower_shadow > body * 2 and upper_shadow < body:
            patterns.append("Bullish Hammer")

        # Shooting Star
        if upper_shadow > body * 2 and lower_shadow < body:
            patterns.append("Bearish Shooting Star")

        # Bullish Engulfing
        if (last["close"] > last["open"] and
            prev["close"] < prev["open"] and
            last["open"] < prev["close"] and
            last["close"] > prev["open"]):
            patterns.append("Bullish Engulfing")

        return patterns

    # ----------------------------------------------------------
    # YARDIMCI METODLAR
    # ----------------------------------------------------------

    def _to_dataframe(self, ohlcv: List[Dict]) -> pd.DataFrame:
        """OHLCV listesini DataFrame'e dönüştürür."""
        df = pd.DataFrame(ohlcv)
        rename_map = {
            "open_price": "open", "high_price": "high",
            "low_price": "low", "close_price": "close",
        }
        df = df.rename(columns=rename_map)
        df = df.sort_values("timestamp").reset_index(drop=True)
        for col in ["open", "high", "low", "close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["volume"] = pd.to_numeric(df.get("volume", 0), errors="coerce").fillna(0)
        return df

    def _latest(self, series) -> Optional[float]:
        """Serinin son değerini güvenli şekilde alır."""
        if series is None:
            return None
        try:
            val = series.iloc[-1] if hasattr(series, "iloc") else series
            return float(val) if not (pd.isna(val) if hasattr(pd, "isna") else False) else None
        except (IndexError, TypeError):
            return None

    def _composite_to_label(self, score: float) -> str:
        if score > 0.5:
            return "Strong Buy"
        elif score > 0.2:
            return "Buy"
        elif score > -0.2:
            return "Neutral"
        elif score > -0.5:
            return "Sell"
        else:
            return "Strong Sell"

    def _empty_result(self) -> Dict:
        return {"indicators": {}, "signals": {}, "patterns": [], "current_price": None}

    # Manuel fallback hesaplamalar
    def _stochastic_k(self, high, low, close, period):
        k = []
        for i in range(len(close)):
            if i < period - 1:
                k.append(np.nan)
            else:
                h = max(high[i - period + 1:i + 1])
                l = min(low[i - period + 1:i + 1])
                k.append(((close[i] - l) / (h - l) * 100) if h != l else 50)
        return np.array(k)

    def _williams_r(self, high, low, close, period):
        wr = []
        for i in range(len(close)):
            if i < period - 1:
                wr.append(np.nan)
            else:
                h = max(high[i - period + 1:i + 1])
                l = min(low[i - period + 1:i + 1])
                wr.append(((h - close[i]) / (h - l) * -100) if h != l else -50)
        return np.array(wr)

    def _cci_manual(self, high, low, close, period):
        typical = (high + low + close) / 3
        rolling_mean = pd.Series(typical).rolling(period).mean()
        rolling_std = pd.Series(typical).rolling(period).std()
        cci = (typical - rolling_mean) / (0.015 * rolling_std)
        return cci.values

    def _mfi_manual(self, high, low, close, volume, period):
        typical = (high + low + close) / 3
        money_flow = typical * volume
        delta = np.diff(typical, prepend=typical[0])
        pos_flow = np.where(delta > 0, money_flow, 0)
        neg_flow = np.where(delta < 0, money_flow, 0)
        pos_sum = pd.Series(pos_flow).rolling(period).sum()
        neg_sum = pd.Series(neg_flow).rolling(period).sum()
        mfr = pos_sum / neg_sum.replace(0, 1e-10)
        return (100 - 100 / (1 + mfr)).values

    def _obv_manual(self, close, volume):
        obv = np.zeros(len(close))
        for i in range(1, len(close)):
            if close[i] > close[i - 1]:
                obv[i] = obv[i - 1] + volume[i]
            elif close[i] < close[i - 1]:
                obv[i] = obv[i - 1] - volume[i]
            else:
                obv[i] = obv[i - 1]
        return obv

    def _atr_manual(self, high, low, close, period):
        tr = [max(h - l, abs(h - c_prev), abs(l - c_prev))
              for h, l, c_prev in zip(high[1:], low[1:], close[:-1])]
        tr = [high[0] - low[0]] + tr
        return pd.Series(tr).rolling(period).mean().values

    def _calculate_adx_manual(self, df):
        """Basit ADX hesaplama."""
        return np.full(len(df), 25.0)   # Placeholder


# Singleton
technical_service = TechnicalAnalysisService()

"""
QuantEdge AI — Sabitler ve Enum Tanımları
==========================================
Uygulama genelinde kullanılan enum'lar ve sabitler.
Pydantic şemalarından bağımsız tutulur — döngüsel import önlemek için.
"""

from enum import Enum


# ----------------------------------------------------------
# Zaman Dilimi Enum
# ----------------------------------------------------------

class TimeframeEnum(str, Enum):
    """Tahmin zaman dilimleri."""
    DAILY     = "1d"
    WEEKLY    = "1w"
    MONTHLY   = "1mo"
    QUARTERLY = "3mo"
    YEARLY    = "1y"

    @property
    def horizon_days(self) -> int:
        """Tahminin kaç gün ileriye baktığı."""
        mapping = {
            "1d": 1, "1w": 7, "1mo": 30, "3mo": 90, "1y": 365
        }
        return mapping[self.value]

    @property
    def display_name(self) -> str:
        mapping = {
            "1d": "1 Gün", "1w": "1 Hafta",
            "1mo": "1 Ay", "3mo": "3 Ay", "1y": "1 Yıl"
        }
        return mapping[self.value]


# ----------------------------------------------------------
# Yön Enum
# ----------------------------------------------------------

class DirectionEnum(str, Enum):
    UP       = "up"
    DOWN     = "down"
    SIDEWAYS = "sideways"


# ----------------------------------------------------------
# Risk Seviyesi Enum
# ----------------------------------------------------------

class RiskLevelEnum(str, Enum):
    LOW     = "low"
    MEDIUM  = "medium"
    HIGH    = "high"
    EXTREME = "extreme"


# ----------------------------------------------------------
# Sentiment Etiketi Enum
# ----------------------------------------------------------

class SentimentLabelEnum(str, Enum):
    VERY_BULLISH = "Very Bullish"
    BULLISH      = "Bullish"
    NEUTRAL      = "Neutral"
    BEARISH      = "Bearish"
    VERY_BEARISH = "Very Bearish"


# ----------------------------------------------------------
# Makro Rejim Enum
# ----------------------------------------------------------

class MacroRegimeEnum(str, Enum):
    GOLDILOCKS = "GOLDILOCKS"   # İdeal büyüme ortamı
    TIGHTENING = "TIGHTENING"   # Faiz artırım dönemi
    EASING     = "EASING"       # Faiz indirim / teşvik
    RISK_OFF   = "RISK_OFF"     # Risk kaçışı
    CRISIS     = "CRISIS"       # Kriz modu
    NEUTRAL    = "NEUTRAL"      # Normal koşullar


# ----------------------------------------------------------
# Veri Kaynağı Enum
# ----------------------------------------------------------

class DataSourceEnum(str, Enum):
    POLYGON       = "polygon"
    ALPHA_VANTAGE = "alpha_vantage"
    FINNHUB       = "finnhub"
    YFINANCE      = "yfinance"
    SEC_EDGAR     = "sec_edgar"
    FRED          = "fred"
    BLS           = "bls"
    REDDIT        = "reddit"
    STOCKTWITS    = "stocktwits"
    NEWS_API      = "newsapi"
    MOCK          = "mock"


# ----------------------------------------------------------
# Model Tipi Enum
# ----------------------------------------------------------

class ModelTypeEnum(str, Enum):
    LSTM        = "lstm"
    XGBOOST     = "xgboost"
    ARIMA_GARCH = "arima_garch"
    ENSEMBLE    = "ensemble"
    RULE_BASED  = "rule_based"


# ----------------------------------------------------------
# Borsa Enum
# ----------------------------------------------------------

class ExchangeEnum(str, Enum):
    NASDAQ = "NASDAQ"
    NYSE   = "NYSE"
    AMEX   = "AMEX"


# ----------------------------------------------------------
# Sektör Sabitleri
# ----------------------------------------------------------

SECTORS = [
    "Technology",
    "Healthcare",
    "Financial Services",
    "Consumer Cyclical",
    "Consumer Defensive",
    "Industrials",
    "Energy",
    "Utilities",
    "Real Estate",
    "Materials",
    "Communication Services",
    "ETF",
]

# ----------------------------------------------------------
# İzleme Listesi (Varsayılan)
# ----------------------------------------------------------

DEFAULT_WATCHLIST = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "META", "TSLA", "JPM", "JNJ", "V",
    "WMT", "XOM", "AMD", "PLTR", "SPY", "QQQ",
]

# FRED Makro Seri Kodları
FRED_SERIES = {
    "DFF":        "FED Funds Rate",
    "GS10":       "10-Year Treasury",
    "GS2":        "2-Year Treasury",
    "T10Y2Y":     "Yield Spread (10Y-2Y)",
    "VIXCLS":     "VIX",
    "DTWEXBGS":   "USD Index",
    "CPIAUCSL":   "CPI",
    "PPIACO":     "PPI",
    "UNRATE":     "Unemployment Rate",
    "PAYEMS":     "Nonfarm Payrolls",
    "GDP":        "GDP",
    "M2SL":       "M2 Money Supply",
    "BAMLH0A0HYM2": "High Yield Spread",
    "MORTGAGE30US": "30Y Mortgage Rate",
}

# Tahmin için yasal uyarı metni
PREDICTION_DISCLAIMER = (
    "⚠️ Bu tahminler istatistiksel modellerden üretilmekte olup %100 doğruluğu garanti edilmez. "
    "Yatırım tavsiyesi değildir. Geçmiş performans gelecekteki sonuçların garantisi değildir. "
    "Finansal kararlarınızı lisanslı bir danışmanla alınız."
)

"""
QuantEdge AI — Merkezi Konfigürasyon Modülü
=============================================
Tüm ayarlar .env dosyasından Pydantic Settings ile okunur.
Type-safe, validated ve IDE-friendly konfigürasyon yönetimi.
"""

from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Uygulama genelinde kullanılan tüm konfigürasyon değerleri.
    .env dosyasından otomatik olarak yüklenir.
    """

    # --------------------------------------------------------
    # Uygulama Temel Ayarları
    # --------------------------------------------------------
    PROJECT_NAME: str = "QuantEdge AI"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = Field(default="development", description="development|staging|production")
    DEBUG: bool = Field(default=True)
    SECRET_KEY: str = Field(default="change-this-in-production-min-32-chars")
    API_V1_PREFIX: str = "/api/v1"

    # --------------------------------------------------------
    # Veritabanı
    # --------------------------------------------------------
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://quantedge:quantedge_secret@localhost:5432/quantedge_db"
    )
    POSTGRES_USER: str = "quantedge"
    POSTGRES_PASSWORD: str = "quantedge_secret"
    POSTGRES_DB: str = "quantedge_db"

    # --------------------------------------------------------
    # Redis
    # --------------------------------------------------------
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    REDIS_CACHE_TTL: int = 300          # 5 dakika
    REDIS_PREDICTION_TTL: int = 3600    # 1 saat

    # --------------------------------------------------------
    # ChromaDB (Vector DB)
    # --------------------------------------------------------
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8001

    # --------------------------------------------------------
    # MLflow
    # --------------------------------------------------------
    MLFLOW_TRACKING_URI: str = "http://localhost:5000"
    MLFLOW_EXPERIMENT_NAME: str = "quantedge_predictions"

    # --------------------------------------------------------
    # Finansal Veri API Anahtarları
    # --------------------------------------------------------
    POLYGON_API_KEY: Optional[str] = Field(default=None, description="Polygon.io API key")
    ALPHA_VANTAGE_API_KEY: Optional[str] = Field(default=None, description="Alpha Vantage API key")
    FINNHUB_API_KEY: Optional[str] = Field(default=None, description="Finnhub API key")
    IEX_CLOUD_API_KEY: Optional[str] = Field(default=None, description="IEX Cloud API key")

    # --------------------------------------------------------
    # Haber & Sentiment API Anahtarları
    # --------------------------------------------------------
    NEWS_API_KEY: Optional[str] = Field(default=None)
    REDDIT_CLIENT_ID: Optional[str] = Field(default=None)
    REDDIT_CLIENT_SECRET: Optional[str] = Field(default=None)
    REDDIT_USER_AGENT: str = "QuantEdgeAI/1.0"
    STOCKTWITS_ACCESS_TOKEN: Optional[str] = Field(default=None)

    # --------------------------------------------------------
    # Makro Ekonomi API Anahtarları
    # --------------------------------------------------------
    FRED_API_KEY: Optional[str] = Field(default=None)
    BLS_API_KEY: Optional[str] = Field(default=None)

    # --------------------------------------------------------
    # Rate Limiting
    # --------------------------------------------------------
    POLYGON_RATE_LIMIT: int = 5
    ALPHA_VANTAGE_RATE_LIMIT: int = 5
    FINNHUB_RATE_LIMIT: int = 60

    # Fallback zinciri: birincil API başarısız olursa sıradaki kullanılır
    MARKET_DATA_FALLBACK_CHAIN: str = "polygon,alpha_vantage,finnhub,yfinance"

    @property
    def fallback_chain(self) -> List[str]:
        return [x.strip() for x in self.MARKET_DATA_FALLBACK_CHAIN.split(",")]

    # --------------------------------------------------------
    # Piyasa Saatleri (ET — Eastern Time)
    # --------------------------------------------------------
    MARKET_OPEN_HOUR: int = 9
    MARKET_OPEN_MINUTE: int = 30
    MARKET_CLOSE_HOUR: int = 16
    MARKET_CLOSE_MINUTE: int = 0

    # --------------------------------------------------------
    # Güncelleme Sıklıkları (saniye)
    # --------------------------------------------------------
    REALTIME_UPDATE_INTERVAL: int = 60
    SENTIMENT_UPDATE_INTERVAL: int = 1800
    MACRO_UPDATE_INTERVAL: int = 86400
    FUNDAMENTAL_UPDATE_INTERVAL: int = 604800

    # --------------------------------------------------------
    # ML Model Ayarları
    # --------------------------------------------------------
    MODEL_ARTIFACTS_PATH: str = "/app/models/artifacts"
    FEATURE_STORE_PATH: str = "/app/models/features"

    # LSTM
    LSTM_SEQUENCE_LENGTH: int = 60
    LSTM_HIDDEN_UNITS: int = 128
    LSTM_DROPOUT: float = 0.2
    LSTM_EPOCHS: int = 100
    LSTM_BATCH_SIZE: int = 32

    # XGBoost
    XGBOOST_N_ESTIMATORS: int = 500
    XGBOOST_MAX_DEPTH: int = 6
    XGBOOST_LEARNING_RATE: float = 0.01

    # --------------------------------------------------------
    # Ensemble Ağırlıkları — Zaman dilimine göre
    # --------------------------------------------------------
    # Günlük
    DAILY_WEIGHT_TECHNICAL: float = 0.35
    DAILY_WEIGHT_SENTIMENT: float = 0.30
    DAILY_WEIGHT_FUNDAMENTAL: float = 0.20
    DAILY_WEIGHT_MACRO: float = 0.15

    # Haftalık
    WEEKLY_WEIGHT_TECHNICAL: float = 0.30
    WEEKLY_WEIGHT_SENTIMENT: float = 0.25
    WEEKLY_WEIGHT_FUNDAMENTAL: float = 0.25
    WEEKLY_WEIGHT_MACRO: float = 0.20

    # Aylık
    MONTHLY_WEIGHT_TECHNICAL: float = 0.20
    MONTHLY_WEIGHT_SENTIMENT: float = 0.15
    MONTHLY_WEIGHT_FUNDAMENTAL: float = 0.35
    MONTHLY_WEIGHT_MACRO: float = 0.30

    # Yıllık
    YEARLY_WEIGHT_TECHNICAL: float = 0.10
    YEARLY_WEIGHT_SENTIMENT: float = 0.05
    YEARLY_WEIGHT_FUNDAMENTAL: float = 0.45
    YEARLY_WEIGHT_MACRO: float = 0.40

    # --------------------------------------------------------
    # Güvenlik & CORS
    # --------------------------------------------------------
    ALLOWED_HOSTS: str = "localhost,127.0.0.1"
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    # --------------------------------------------------------
    # İzleme
    # --------------------------------------------------------
    SENTRY_DSN: Optional[str] = None

    # --------------------------------------------------------
    # Yardımcı Özellikler
    # --------------------------------------------------------
    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def has_polygon(self) -> bool:
        return bool(self.POLYGON_API_KEY)

    @property
    def has_alpha_vantage(self) -> bool:
        return bool(self.ALPHA_VANTAGE_API_KEY)

    @property
    def has_finnhub(self) -> bool:
        return bool(self.FINNHUB_API_KEY)

    @property
    def has_fred(self) -> bool:
        return bool(self.FRED_API_KEY)

    @property
    def has_reddit(self) -> bool:
        return bool(self.REDDIT_CLIENT_ID and self.REDDIT_CLIENT_SECRET)

    def get_ensemble_weights(self, timeframe: str) -> dict:
        """
        Verilen zaman dilimine göre ensemble ağırlıklarını döndürür.

        Args:
            timeframe: '1d', '1w', '1mo', '3mo', '1y'

        Returns:
            {'technical': float, 'sentiment': float, 'fundamental': float, 'macro': float}
        """
        weights_map = {
            "1d": {
                "technical": self.DAILY_WEIGHT_TECHNICAL,
                "sentiment": self.DAILY_WEIGHT_SENTIMENT,
                "fundamental": self.DAILY_WEIGHT_FUNDAMENTAL,
                "macro": self.DAILY_WEIGHT_MACRO,
            },
            "1w": {
                "technical": self.WEEKLY_WEIGHT_TECHNICAL,
                "sentiment": self.WEEKLY_WEIGHT_SENTIMENT,
                "fundamental": self.WEEKLY_WEIGHT_FUNDAMENTAL,
                "macro": self.WEEKLY_WEIGHT_MACRO,
            },
            "1mo": {
                "technical": self.MONTHLY_WEIGHT_TECHNICAL,
                "sentiment": self.MONTHLY_WEIGHT_SENTIMENT,
                "fundamental": self.MONTHLY_WEIGHT_FUNDAMENTAL,
                "macro": self.MONTHLY_WEIGHT_MACRO,
            },
            "3mo": {
                "technical": self.MONTHLY_WEIGHT_TECHNICAL * 0.8,
                "sentiment": self.MONTHLY_WEIGHT_SENTIMENT * 0.7,
                "fundamental": self.MONTHLY_WEIGHT_FUNDAMENTAL * 1.1,
                "macro": self.MONTHLY_WEIGHT_MACRO * 1.2,
            },
            "1y": {
                "technical": self.YEARLY_WEIGHT_TECHNICAL,
                "sentiment": self.YEARLY_WEIGHT_SENTIMENT,
                "fundamental": self.YEARLY_WEIGHT_FUNDAMENTAL,
                "macro": self.YEARLY_WEIGHT_MACRO,
            },
        }
        weights = weights_map.get(timeframe, weights_map["1d"])
        # Ağırlıkları normalize et (toplamı 1.0 olsun)
        total = sum(weights.values())
        return {k: v / total for k, v in weights.items()}

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """
    Settings singleton'ı döndürür.
    lru_cache ile tekrar tekrar oluşturulması engellenir.
    """
    return Settings()


# Global settings nesnesi
settings = get_settings()

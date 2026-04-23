"""
QuantEdge AI — FastAPI Ana Uygulama
====================================
Uygulama giriş noktası. Router'ları, middleware'leri ve
başlangıç/kapanış event'lerini yönetir.
"""

import asyncio
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import ORJSONResponse
from prometheus_client import make_asgi_app

from app.api.v1.endpoints import health, macro, market, sentiment, stocks
from app.core.cache import cache_manager
from app.core.config import settings
from app.core.logging import setup_logging
from app.models.database import create_tables

# Yapılandırılmış loglama kurulumu
setup_logging()
logger = structlog.get_logger()


# ----------------------------------------------------------
# Lifespan: Uygulama başlangıç ve kapanış event'leri
# ----------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Uygulama yaşam döngüsü yöneticisi.
    Başlangıçta bağlantılar kurulur, kapanışta temizlenir.
    """
    # ---- BAŞLANGIÇ ----
    logger.info("QuantEdge AI başlatılıyor...", version="1.0.0", env=settings.ENVIRONMENT)

    # Veritabanı tablolarını oluştur
    await create_tables()
    logger.info("Veritabanı tabloları hazır.")

    # Redis bağlantısını başlat
    await cache_manager.connect()
    logger.info("Redis bağlantısı kuruldu.")

    # İlk veri yükleme kontrolü (gerekirse)
    if settings.ENVIRONMENT == "development":
        logger.info("Development modunda başlatılıyor — mock veriler aktif.")

    logger.info("✅ QuantEdge AI hazır!", host="0.0.0.0", port=8000)

    yield  # Uygulama çalışır

    # ---- KAPANIŞ ----
    logger.info("QuantEdge AI kapatılıyor...")
    await cache_manager.disconnect()
    logger.info("Redis bağlantısı kapatıldı.")
    logger.info("👋 QuantEdge AI durduruldu.")


# ----------------------------------------------------------
# FastAPI Uygulaması
# ----------------------------------------------------------
app = FastAPI(
    title="QuantEdge AI",
    description="""
    ## 📈 QuantEdge AI — ABD Borsa Tahmin Platformu

    ABD borsalarındaki (NASDAQ, NYSE) hisse senetlerinin fiyat hareketlerini
    teknik analiz, temel analiz, sentiment analizi ve makroekonomik faktörler
    kullanarak yapay zeka ile tahmin eden platform.

    ### Özellikler
    - **Çoklu Zaman Dilimi**: Günlük, haftalık, aylık, 3 aylık, yıllık
    - **Ensemble ML**: LSTM + XGBoost + ARIMA kombinasyonu
    - **Gerçek Zamanlı Veri**: Polygon.io, Alpha Vantage, FRED entegrasyonu
    - **Sentiment Analizi**: Reddit, StockTwits, Haber API'leri
    - **Risk Yönetimi**: Anomali tespiti, Black Swan uyarıları

    ### ⚠️ Yasal Uyarı
    Bu platform yalnızca eğitim amaçlıdır. Yatırım tavsiyesi değildir.
    Tüm tahminler istatistiksel modellerden üretilmekte olup %100 doğruluğu
    garanti edilmez. Lütfen finansal kararlarınızı lisanslı danışmanlarla alın.
    """,
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    default_response_class=ORJSONResponse,  # Hızlı JSON yanıtları için
    lifespan=lifespan,
)

# ----------------------------------------------------------
# Middleware Yapılandırması
# ----------------------------------------------------------

# CORS — Frontend erişimi için
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GZip sıkıştırma (büyük veri yanıtları için)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# ----------------------------------------------------------
# Prometheus Metrics (izleme)
# ----------------------------------------------------------
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# ----------------------------------------------------------
# API Router'ları
# ----------------------------------------------------------
app.include_router(
    health.router,
    prefix="/api/v1",
    tags=["🏥 Health"],
)

app.include_router(
    stocks.router,
    prefix="/api/v1/stocks",
    tags=["📈 Stocks & Predictions"],
)

app.include_router(
    market.router,
    prefix="/api/v1/market",
    tags=["📊 Market Data"],
)

app.include_router(
    sentiment.router,
    prefix="/api/v1/sentiment",
    tags=["💬 Sentiment Analysis"],
)

app.include_router(
    macro.router,
    prefix="/api/v1/macro",
    tags=["🌍 Macro Economics"],
)


# ----------------------------------------------------------
# Kök endpoint
# ----------------------------------------------------------
@app.get("/", tags=["Root"])
async def root():
    """Uygulama bilgisi döndürür."""
    return {
        "name": "QuantEdge AI",
        "version": "1.0.0",
        "status": "running",
        "docs": "/api/docs",
        "disclaimer": (
            "Bu platform yalnızca eğitim amaçlıdır. "
            "Yatırım tavsiyesi değildir."
        ),
    }


# ----------------------------------------------------------
# Geliştirici başlatma
# ----------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )

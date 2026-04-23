# QuantEdge AI — System Architecture

## 🏛️ Mimari Genel Bakış

QuantEdge AI, mikroservis-inspired monolith (modular monolith) mimarisi üzerine inşa edilmiştir.
Geleneksel mikroservis karmaşıklığı olmadan, modüler ve ölçeklenebilir bir yapı sunar.

---

## 📐 Sistem Akış Diyagramı (ASCII)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           QUANTEDGE AI PLATFORM                                 │
└─────────────────────────────────────────────────────────────────────────────────┘

╔══════════════════════════════════════════════════════════════════════════════════╗
║                         EXTERNAL DATA SOURCES                                  ║
╠══════════════╦═══════════════╦══════════════╦══════════════╦════════════════════╣
║  MARKET DATA ║  FUNDAMENTAL  ║  SENTIMENT   ║    MACRO     ║   ALTERNATIVE      ║
║  ─────────── ║  ───────────  ║  ─────────── ║  ─────────   ║   ──────────────── ║
║  Polygon.io  ║  SEC EDGAR   ║  Reddit API  ║  FRED API    ║  Unusual Whales    ║
║  Alpha Vant. ║  Alpha Vant. ║  StockTwits  ║  BLS API     ║  Dark Pool Data    ║
║  Yahoo Fin.  ║  Finnhub     ║  NewsAPI     ║  Treasury    ║  Options Flow      ║
║  IEX Cloud   ║  Finnhub     ║  GDELT       ║  API         ║  Insider Trans.    ║
╚══════════════╩═══════════════╩══════════════╩══════════════╩════════════════════╝
         │                │              │              │              │
         └────────────────┴──────────────┴──────────────┴──────────────┘
                                         │
                              ┌──────────▼──────────┐
                              │   DATA INGESTION     │
                              │   LAYER (Celery +    │
                              │   Redis Queue)       │
                              │                      │
                              │  ┌────────────────┐  │
                              │  │  Rate Limiter  │  │
                              │  │  Retry Logic   │  │
                              │  │  Fallback Mgr  │  │
                              │  └────────────────┘  │
                              └──────────┬───────────┘
                                         │
                    ┌────────────────────┼──────────────────────┐
                    │                    │                       │
           ┌────────▼───────┐  ┌────────▼───────┐  ┌──────────▼──────┐
           │  TIMESERIES DB │  │  VECTOR DB      │  │  RELATIONAL DB  │
           │  (TimescaleDB) │  │  (ChromaDB /    │  │  (PostgreSQL)   │
           │                │  │   Qdrant)       │  │                 │
           │  OHLCV Data    │  │  News Embed.    │  │  Users, Jobs    │
           │  Indicators    │  │  Sentiment Vecs │  │  Predictions    │
           │  Macro Metrics │  │  RAG Context    │  │  Model Results  │
           └────────┬───────┘  └────────┬───────┘  └──────────┬──────┘
                    │                    │                       │
                    └────────────────────┼──────────────────────┘
                                         │
                              ┌──────────▼──────────┐
                              │   FEATURE ENGINEERING│
                              │   PIPELINE           │
                              │                      │
                              │  Technical Features  │
                              │  Fundamental Ratios  │
                              │  Sentiment Scores    │
                              │  Macro Indicators    │
                              │  Cross-Asset Signals │
                              └──────────┬───────────┘
                                         │
                    ┌────────────────────┼──────────────────────┐
                    │                    │                       │
           ┌────────▼───────┐  ┌────────▼───────┐  ┌──────────▼──────┐
           │  TIME-SERIES   │  │  CLASSICAL ML   │  │  DEEP LEARNING  │
           │  MODELS        │  │  MODELS         │  │  MODELS         │
           │                │  │                 │  │                 │
           │  ARIMA/SARIMA  │  │  XGBoost        │  │  LSTM/BiLSTM   │
           │  GARCH         │  │  LightGBM       │  │  Transformer   │
           │  Prophet       │  │  Random Forest  │  │  Temporal       │
           │                │  │                 │  │  Fusion Net     │
           └────────┬───────┘  └────────┬───────┘  └──────────┬──────┘
                    │                    │                       │
                    └────────────────────┼──────────────────────┘
                                         │
                              ┌──────────▼──────────┐
                              │  ENSEMBLE ENGINE     │
                              │                      │
                              │  Stacking Regressor  │
                              │  Time-weighted       │
                              │  Bayesian Averaging  │
                              │  Confidence Bands    │
                              │  Anomaly Detection   │
                              └──────────┬───────────┘
                                         │
                              ┌──────────▼──────────┐
                              │   REDIS CACHE        │
                              │   (Results + API)    │
                              └──────────┬───────────┘
                                         │
                    ┌────────────────────┼──────────────────────┐
                    │                    │                       │
           ┌────────▼───────┐  ┌────────▼───────┐  ┌──────────▼──────┐
           │  FastAPI        │  │  MLflow         │  │  Monitoring     │
           │  REST API      │  │  Tracking        │  │  (Prometheus +  │
           │  (v1)          │  │  & Registry      │  │   Grafana)      │
           └────────┬───────┘  └────────────────┘  └─────────────────┘
                    │
           ┌────────▼───────────────────────────────────────────┐
           │                 NEXT.JS FRONTEND                    │
           │                                                      │
           │  ┌─────────────┐  ┌──────────────┐  ┌───────────┐  │
           │  │  Dashboard  │  │  TradingView  │  │  Insights │  │
           │  │  Stock Sel. │  │  Charts       │  │  Panel    │  │
           │  │  Screener   │  │  Indicators   │  │  AI Exp.  │  │
           │  └─────────────┘  └──────────────┘  └───────────┘  │
           └──────────────────────────────────────────────────────┘
```

---

## 🧱 Katman Mimarisi

### Layer 1: Data Ingestion
- **Celery Workers** ile asenkron veri çekme
- **Redis** görev kuyruğu ve önbellekleme
- **Rate limiter** + exponential backoff retry
- **Fallback chain**: Primary API → Secondary API → Cache → Mock

### Layer 2: Storage
- **TimescaleDB** (PostgreSQL extension): OHLCV ve zaman serisi veriler
- **ChromaDB / Qdrant**: Haber embedding'leri, RAG için vector store
- **PostgreSQL**: Kullanıcı verileri, tahmin kayıtları, model metadata

### Layer 3: Feature Engineering
- Teknik göstergeler (TA-Lib)
- NLP sentiment scoring (FinBERT)
- Makro normalizasyon pipeline'ı

### Layer 4: ML Engine
- **MLflow** ile experiment tracking ve model registry
- Time-weighted ensemble: günlükte teknik+sentiment ağırlıklı, yıllıkta makro+fundamental ağırlıklı

### Layer 5: API & Frontend
- **FastAPI** async REST API
- **Next.js 14** App Router ile SSR + client-side interactivity

---

## 🔧 Uzman Revizyonları (Senior Architect Notları)

| Gereksinim | Orijinal Öneri | Uzman Tercihi | Neden? |
|---|---|---|---|
| Sentiment Store | Basit DB | **ChromaDB (Vector DB)** | RAG pipeline ile geçmiş haberler semantik arama ile sorgulanabilir |
| Task Queue | Celery + Redis | **Celery + Redis Streams** | Redis Streams, Kafka benzeri güvenilir mesaj geçmişi sunar |
| Time Series DB | PostgreSQL | **TimescaleDB** | 100x daha hızlı OHLCV sorgulama, otomatik veri sıkıştırma |
| ML Tracking | Manuel log | **MLflow** | Otomatik experiment tracking, model versioning, A/B testing |
| NLP Sentiment | VADER/TextBlob | **FinBERT** | Finansal domain için fine-tuned BERT, çok daha doğru |
| Makro Veri | Manuel fetch | **FRED API + BLS API** | Resmi kaynak, 800,000+ zaman serisi, güvenilir |
| Anomali Tespiti | Threshold-based | **Isolation Forest + LSTM Autoencoder** | Unsupervised, "Black Swan" olayları için robust |

---

## 📁 Proje Klasör Yapısı

```
quantedge/
├── 📂 backend/
│   ├── 📂 app/
│   │   ├── 📂 api/
│   │   │   └── 📂 v1/
│   │   │       └── 📂 endpoints/
│   │   │           ├── stocks.py        # Hisse tahmin endpoint'leri
│   │   │           ├── market.py        # Piyasa verisi endpoint'leri
│   │   │           ├── sentiment.py     # Duygu analizi endpoint'leri
│   │   │           ├── macro.py         # Makroekonomik veri endpoint'leri
│   │   │           └── health.py        # Health check
│   │   ├── 📂 core/
│   │   │   ├── config.py               # Ayarlar ve ortam değişkenleri
│   │   │   ├── security.py             # API key yönetimi
│   │   │   ├── cache.py                # Redis cache yöneticisi
│   │   │   └── logging.py              # Yapılandırılmış loglama
│   │   ├── 📂 models/
│   │   │   ├── database.py             # SQLAlchemy modelleri
│   │   │   ├── schemas.py              # Pydantic şemaları
│   │   │   └── enums.py                # Sabitler ve enum'lar
│   │   ├── 📂 services/
│   │   │   ├── 📂 data_fetchers/
│   │   │   │   ├── market_data.py      # Polygon, Alpha Vantage, yfinance
│   │   │   │   ├── fundamental.py      # SEC EDGAR, Finnhub
│   │   │   │   ├── sentiment.py        # Reddit, StockTwits, NewsAPI
│   │   │   │   ├── macro.py            # FRED API, BLS
│   │   │   │   └── fallback.py         # Fallback/mock veri yöneticisi
│   │   │   ├── 📂 ml/
│   │   │   │   ├── feature_engineering.py
│   │   │   │   ├── models/
│   │   │   │   │   ├── lstm_model.py
│   │   │   │   │   ├── xgboost_model.py
│   │   │   │   │   ├── arima_model.py
│   │   │   │   │   └── ensemble.py
│   │   │   │   ├── training.py
│   │   │   │   └── prediction.py
│   │   │   └── 📂 analysis/
│   │   │       ├── technical.py        # TA göstergeleri
│   │   │       ├── fundamental.py      # Temel analiz hesaplamaları
│   │   │       ├── sentiment_nlp.py    # FinBERT pipeline
│   │   │       ├── anomaly.py          # Anomali tespiti
│   │   │       └── risk.py             # Risk metrikleri
│   │   ├── 📂 tasks/
│   │   │   ├── celery_app.py           # Celery konfigürasyonu
│   │   │   ├── data_tasks.py           # Periyodik veri çekme görevleri
│   │   │   └── prediction_tasks.py     # ML tahmin görevleri
│   │   └── 📂 utils/
│   │       ├── rate_limiter.py
│   │       ├── retry.py
│   │       └── validators.py
│   ├── 📂 tests/
│   ├── requirements.txt
│   ├── Dockerfile
│   └── main.py
├── 📂 frontend/
│   ├── 📂 src/
│   │   ├── 📂 app/                     # Next.js App Router
│   │   ├── 📂 components/
│   │   ├── 📂 hooks/
│   │   ├── 📂 lib/
│   │   └── 📂 store/                   # Zustand global state
│   ├── package.json
│   └── Dockerfile
├── 📂 infrastructure/
│   ├── docker-compose.yml
│   ├── docker-compose.prod.yml
│   └── 📂 nginx/
├── 📂 scripts/
│   ├── init_db.py
│   ├── seed_data.py
│   └── train_models.py
├── .env.example
├── .gitignore
└── README.md
```

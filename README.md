# QuantEdge AI 📈

> **ABD Borsası Yapay Zeka Tahmin Platformu**
> NASDAQ & NYSE · BiLSTM + XGBoost + ARIMA · Ensemble ML

---

## ⚠️ Yasal Uyarı

Bu proje **yalnızca eğitim amaçlıdır**. Sunulan tahminler **yatırım tavsiyesi değildir**. Finansal kararlarınızı lisanslı danışmanlarla alınız.

---

## 🚀 Hızlı Başlangıç

```bash
# 1. Klonla
git clone https://github.com/yourname/quantedge-ai.git
cd quantedge-ai

# 2. Ortam değişkenlerini ayarla
cp .env.example .env
# .env içinde SECRET_KEY ve isteğe bağlı API anahtarlarını gir

# 3. Docker ile başlat
cd infrastructure
docker compose up -d

# 4. Erişim
# Frontend : http://localhost:3000
# API Docs : http://localhost:8000/api/docs
# MLflow   : http://localhost:5000
```

---

## 🏗️ Mimari

```
Dış API'ler (Polygon · FRED · Reddit · SEC EDGAR · Finnhub)
        ↓
Celery + Redis  ←  Asenkron veri toplama, periyodik görevler
        ↓
TimescaleDB · ChromaDB (RAG) · PostgreSQL
        ↓
Feature Engineering (74 özellik: fiyat/teknik/sentiment/makro/temel)
        ↓
BiLSTM + Attention  ·  XGBoost + Optuna  ·  ARIMA/GARCH
        ↓
Ensemble Engine  →  Anomali Tespiti  →  Risk Değerlendirme
        ↓
FastAPI REST  ←→  MLflow Tracking
        ↓
Next.js 14 Dashboard  (TradingView Lightweight Charts)
```

---

## 📦 Servisler

| Servis | URL | Açıklama |
|--------|-----|----------|
| Dashboard | http://localhost:3000 | Ana arayüz |
| API Docs | http://localhost:8000/api/docs | Swagger UI |
| MLflow | http://localhost:5000 | Model tracking |
| Flower | http://localhost:5555 | Celery monitor |

---

## 🔑 API Anahtarları (Tamamı Ücretsiz)

| Servis | Kayıt | Oran |
|--------|-------|------|
| Polygon.io | polygon.io/dashboard | 5 req/dk |
| Alpha Vantage | alphavantage.co | 5 req/dk |
| Finnhub | finnhub.io | 60 req/dk |
| FRED | fred.stlouisfed.org | Sınırsız |
| NewsAPI | newsapi.org | 100 req/gün |
| Reddit PRAW | reddit.com/prefs/apps | Ücretsiz |

> API anahtarı olmadan **mock veri** kullanılır (development modda otomatik).

---

## 🤖 ML Modelleri

### Ensemble Ağırlıkları

| Timeframe | BiLSTM | XGBoost | ARIMA/GARCH |
|-----------|--------|---------|-------------|
| 1 Gün | 45% | 40% | 15% |
| 1 Hafta | 40% | 35% | 25% |
| 1 Ay | 30% | 30% | 40% |
| 1 Yıl | 15% | 20% | 65% |

### Mimari Kararlar

| Standart | Seçilen | Neden |
|----------|---------|-------|
| PostgreSQL | **TimescaleDB** | 100x hızlı OHLCV sorgusu |
| SQL store | **ChromaDB** | RAG ile semantik haber arama |
| VADER | **FinBERT** | Finansal domain, %15+ daha doğru |
| Grid search | **Optuna** | Bayesian, 3-5x daha verimli |
| Threshold anomali | **Isolation Forest** | Çok boyutlu, unsupervised |
| Manuel log | **MLflow** | Experiment versioning, A/B test |

---

## 🧪 Testler

```bash
cd backend
pytest tests/ -v
pytest tests/ --cov=app --cov-report=html
```

---

## 💻 Local Geliştirme (Docker Olmadan)

```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload

# Frontend (ayrı terminal)
cd frontend
npm install && npm run dev

# Celery (ayrı terminal)
cd backend
celery -A app.tasks.celery_app worker --loglevel=info
```

---

## 📡 API Örnekleri

```bash
# Tahmin al
curl -X POST http://localhost:8000/api/v1/stocks/predict \
  -H "Content-Type: application/json" \
  -d '{"ticker": "AAPL", "timeframe": "1d"}'

# OHLCV verisi
curl "http://localhost:8000/api/v1/market/AAPL/ohlcv?timeframe=1d"

# Sentiment
curl "http://localhost:8000/api/v1/sentiment/AAPL"

# Makro snapshot
curl "http://localhost:8000/api/v1/macro/snapshot"

# Screener
curl "http://localhost:8000/api/v1/stocks/screener?direction=up&min_confidence=0.65"
```

---

## 🔧 Sorun Giderme

```bash
# Loglar
docker compose logs -f backend

# Redis testi
docker exec quantedge_redis redis-cli ping   # → PONG

# TimescaleDB kontrolü
docker exec quantedge_postgres psql -U quantedge -c "\dx"

# Model eğitimi
docker exec -it quantedge_backend bash
python ../scripts/train_models.py --tickers AAPL --fast
```

---

*MIT License · QuantEdge AI*

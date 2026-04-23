# Event-Aware Forecasting — Uygulama Rehberi

## Değiştirilen / Eklenen Dosyalar

| Dosya | Değişiklik Türü | Açıklama |
|---|---|---|
| `backend/app/services/data_fetchers/events.py` | **YENİ** | Ana event servisi (earnings + makro) |
| `backend/app/data/event_calendar.json` | **YENİ** | 2025-2026 FOMC / CPI statik takvim |
| `backend/app/models/schemas.py` | **PATCH** | `include_events`, `EventContext`, `event_context` alanları |
| `backend/app/services/ml/prediction.py` | **PATCH** | `_apply_event_adjustments()` entegrasyonu |
| `backend/app/api/v1/endpoints/stocks.py` | **PATCH** | Cache key güncellemesi |
| `frontend/src/components/dashboard/EventBadge.tsx` | **YENİ** | Chip/badge bileşeni |
| `frontend/src/lib/api.ts` | **PATCH** | `EventContext` tipi + yeni alanlar |
| `backend/tests/test_events.py` | **YENİ** | Unit testler |

---

## Adım Adım Uygulama

### 1. Yeni Dosyaları Kopyala

```bash
# Proje kök dizininde iken:
cp quantedge-patch/backend/app/services/data_fetchers/events.py \
   c:/quantedge-complete/backend/app/services/data_fetchers/events.py

cp quantedge-patch/backend/app/data/event_calendar.json \
   c:/quantedge-complete/backend/app/data/event_calendar.json

cp quantedge-patch/frontend/src/components/dashboard/EventBadge.tsx \
   c:/quantedge-complete/frontend/src/components/dashboard/EventBadge.tsx

cp quantedge-patch/backend/tests/test_events.py \
   c:/quantedge-complete/backend/tests/test_events.py
```

---

### 2. schemas.py — 3 değişiklik

**a) `PredictionRequest`'e ekle:**
```python
include_events: bool = Field(default=True, description="Factor upcoming events into forecast")
```

**b) Yeni `EventContext` modeli ekle (sınıf olarak):**
```python
class EventContext(BaseModel):
    next_earnings_date: Optional[str] = None
    days_to_next_earnings: Optional[int] = None
    earnings_window: bool = False
    next_fomc_date: Optional[str] = None
    days_to_next_fomc: Optional[int] = None
    fomc_window: bool = False
    next_cpi_date: Optional[str] = None
    days_to_next_cpi: Optional[int] = None
    cpi_window: bool = False
    combined_vol_multiplier: float = 1.0
```

**c) `PredictionResponse`'a ekle:**
```python
event_context: Optional[EventContext] = None
```

---

### 3. prediction.py — 3 ekleme

**a) Import ekle (dosyanın üstüne):**
```python
from backend.app.services.data_fetchers.events import get_event_context
```

**b) `_apply_event_adjustments` fonksiyonunu** `prediction_patch.py`'den kopyala.

**c) Ana `predict()` fonksiyonunun içinde**, `confidence_low/high` hesaplandıktan hemen sonra ekle:
```python
confidence_low, confidence_high, risk_level, event_ctx = (
    await _apply_event_adjustments(
        ticker=request.ticker,
        include_events=getattr(request, "include_events", True),
        predicted_price=predicted_price,
        confidence_low=confidence_low,
        confidence_high=confidence_high,
        risk_level=risk_level,
    )
)
```

**d) Response oluştururken** ekle:
```python
event_context=EventContext(**event_ctx) if event_ctx else None,
```

---

### 4. stocks.py — Cache key güncelle

Mevcut cache key satırını bul (`ticker:timeframe:prediction` içeren satır) ve şunla değiştir:

```python
from datetime import date as _date
_today = _date.today().isoformat()
cache_key = (
    f"{request.ticker}:{request.timeframe}:prediction"
    f":events={int(getattr(request, 'include_events', True))}"
    f":{_today}"
)
```

---

### 5. PredictionPanel.tsx — Badge entegrasyonu

```tsx
// Dosyanın üstüne import ekle:
import EventBadge from "@/components/dashboard/EventBadge";

// JSX içinde, prediction sonucu gösterildikten sonra:
<EventBadge eventContext={prediction?.event_context} />
```

---

### 6. api.ts — Tip güncellemeleri

`api_patch.ts` içindeki `EventContext` interface'ini kopyala.
`PredictionRequest` ve `PredictionResponse` interface'lerine ilgili alanları ekle.

---

### 7. .env — Finnhub API key (opsiyonel ama önerilir)

```env
FINNHUB_API_KEY=your_key_here
```

Finnhub'da ücretsiz hesap aç: https://finnhub.io/register
Key yoksa sistem otomatik olarak yfinance'e düşer.

---

### 8. Bağımlılık kontrolü

```bash
# Backend
pip show httpx yfinance  # ikisi de muhtemelen zaten mevcut
# Değilse:
pip install httpx yfinance
```

---

## Test

### Unit testler

```bash
cd c:/quantedge-complete
pytest backend/tests/test_events.py -v
```

### curl örnekleri

**Temel tahmin (events dahil, varsayılan):**
```bash
curl -X POST http://localhost:8000/api/v1/stocks/predict \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "AAPL",
    "timeframe": "1w",
    "include_technical": true,
    "include_events": true
  }'
```

**Events devre dışı:**
```bash
curl -X POST http://localhost:8000/api/v1/stocks/predict \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "AAPL",
    "timeframe": "1w",
    "include_events": false
  }'
```

**Beklenen response'ta yeni alan:**
```json
{
  "ticker": "AAPL",
  "predicted_price": 195.4,
  "confidence_low": 188.1,
  "confidence_high": 202.7,
  "risk_level": "medium",
  "event_context": {
    "next_earnings_date": "2025-07-31",
    "days_to_next_earnings": 4,
    "earnings_window": true,
    "next_fomc_date": "2025-07-30",
    "days_to_next_fomc": 3,
    "fomc_window": true,
    "next_cpi_date": "2025-08-12",
    "days_to_next_cpi": 16,
    "cpi_window": false,
    "combined_vol_multiplier": 1.95
  }
}
```

---

## Varsayılan Eşik ve Çarpan Değerleri

| Parametre | Değer | Konum |
|---|---|---|
| `EARNINGS_WINDOW_DAYS` | 7 gün | `events.py` satır 24 |
| `FOMC_WINDOW_DAYS` | 5 gün | `events.py` satır 25 |
| `CPI_WINDOW_DAYS` | 5 gün | `events.py` satır 26 |
| `VOL_MULTIPLIER_EARNINGS_NEAR` | ×1.5 | `events.py` satır 28 |
| `VOL_MULTIPLIER_EARNINGS_SOON` | ×1.2 | `events.py` satır 29 |
| `VOL_MULTIPLIER_FOMC_NEAR` | ×1.3 | `events.py` satır 30 |
| `VOL_MULTIPLIER_CPI_NEAR` | ×1.2 | `events.py` satır 31 |

Tüm bu değerleri `events.py` dosyasının üst kısmındaki sabitlerden değiştirebilirsin.

---

## Mimari Özeti

```
POST /predict
  │
  ├─ include_events=True?
  │    └─ get_event_context(ticker)
  │         ├─ get_earnings_calendar()
  │         │    ├─ Finnhub API (önce dene)
  │         │    └─ yfinance (fallback)
  │         └─ get_macro_events()
  │              └─ event_calendar.json (statik)
  │
  ├─ _apply_event_adjustments()
  │    ├─ confidence interval genişlet (× combined_vol_multiplier)
  │    └─ risk_level floor ("low" → "medium" if any window active)
  │
  └─ PredictionResponse { ...mevcut alanlar..., event_context }
```

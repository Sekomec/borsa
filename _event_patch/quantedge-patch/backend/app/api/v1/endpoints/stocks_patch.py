"""
PATCH for backend/app/api/v1/endpoints/stocks.py

Two changes needed:
  1. Add include_events to the PredictionRequest handling (already covered by schema)
  2. Update the cache key so event-sensitive predictions aren't served stale

Apply by finding the cache key line in your existing /predict handler.
"""

# ══════════════════════════════════════════════════════════════════════════
# CACHE KEY PATCH
# ══════════════════════════════════════════════════════════════════════════
# Current cache key (typical):
#   cache_key = f"{ticker}:{timeframe}:prediction"
#
# REPLACE with:
#   from datetime import date
#   _today = date.today().isoformat()          # cache expires naturally each day
#   cache_key = (
#       f"{ticker}:{timeframe}:prediction"
#       f":events={int(getattr(request, 'include_events', True))}"
#       f":{_today}"
#   )
#
# This ensures:
#   • Event-on vs event-off requests are cached separately.
#   • Cache auto-invalidates daily (so stale earnings dates don't persist).
#   • No breaking change to existing logic.
# ══════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════
# FULL HANDLER SKELETON (reference only — merge into your existing handler)
# ══════════════════════════════════════════════════════════════════════════

from datetime import date as _date
from fastapi import APIRouter, HTTPException
# from backend.app.models.schemas import PredictionRequest, PredictionResponse


router = APIRouter()


# @router.post("/predict", response_model=PredictionResponse)
async def predict_stock(request):  # replace type hint with PredictionRequest
    ticker = request.ticker.upper()
    timeframe = request.timeframe

    _today = _date.today().isoformat()
    cache_key = (
        f"{ticker}:{timeframe}:prediction"
        f":events={int(getattr(request, 'include_events', True))}"
        f":{_today}"
    )

    # ... rest of your existing caching / prediction logic unchanged ...
    # At the end, call _apply_event_adjustments() as shown in prediction_patch.py
    pass

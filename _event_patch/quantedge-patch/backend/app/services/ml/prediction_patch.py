"""
PATCH for backend/app/services/ml/prediction.py
Shows the three insertion points needed for event-aware forecasting.

Search for each PATCH MARKER comment and apply the change.
"""

# ══════════════════════════════════════════════════════════════════════════
# PATCH 1 — Add import at top of prediction.py
# ══════════════════════════════════════════════════════════════════════════
# ADD this import alongside existing ones:
#
#   from backend.app.services.data_fetchers.events import get_event_context
#
# (Adjust import path to match your project's module resolution.)


# ══════════════════════════════════════════════════════════════════════════
# PATCH 2 — In the main predict() / generate_prediction() async function
#           Fetch event context BEFORE the confidence interval is built.
# ══════════════════════════════════════════════════════════════════════════

async def _apply_event_adjustments(
    ticker: str,
    include_events: bool,
    predicted_price: float,
    confidence_low: float,
    confidence_high: float,
    risk_level: str,                   # "low" | "medium" | "high"
) -> tuple[float, float, str, dict]:
    """
    Widens the confidence interval and floors risk level based on events.

    Returns:
        (adjusted_low, adjusted_high, adjusted_risk, event_context_dict)
    """
    from backend.app.services.data_fetchers.events import get_event_context  # noqa

    event_ctx: dict = {}

    if not include_events:
        return confidence_low, confidence_high, risk_level, event_ctx

    try:
        event_ctx = await get_event_context(ticker)
    except Exception:
        # Graceful fallback — prediction still works
        return confidence_low, confidence_high, risk_level, event_ctx

    mult = event_ctx.get("combined_vol_multiplier", 1.0)

    if mult > 1.0:
        mid = predicted_price
        half_range_low = mid - confidence_low
        half_range_high = confidence_high - mid

        confidence_low = mid - half_range_low * mult
        confidence_high = mid + half_range_high * mult

        # Floor risk level
        any_window = (
            event_ctx.get("earnings_window")
            or event_ctx.get("fomc_window")
            or event_ctx.get("cpi_window")
        )
        if any_window and risk_level == "low":
            risk_level = "medium"

    return confidence_low, confidence_high, risk_level, event_ctx


# ══════════════════════════════════════════════════════════════════════════
# PATCH 3 — Integration snippet for your existing predict function.
#           Place this AFTER you compute predicted_price / confidence interval
#           and BEFORE you build the final response dict.
# ══════════════════════════════════════════════════════════════════════════
#
# Example (adapt variable names to your existing code):
#
#   confidence_low, confidence_high, risk_level, event_ctx = (
#       await _apply_event_adjustments(
#           ticker=request.ticker,
#           include_events=getattr(request, "include_events", True),
#           predicted_price=predicted_price,
#           confidence_low=confidence_low,
#           confidence_high=confidence_high,
#           risk_level=risk_level,
#       )
#   )
#
#   # Then pass event_ctx into the response:
#   response = PredictionResponse(
#       ...existing fields...,
#       event_context=EventContext(**event_ctx) if event_ctx else None,
#   )

"""
PATCH for backend/app/models/schemas.py
Add the following fields to your existing Pydantic models.
"""

# ── ADD to PredictionRequest ──────────────────────────────────────────────
from pydantic import BaseModel, Field
from typing import Optional


class PredictionRequestAdditions(BaseModel):
    """Copy these fields into your existing PredictionRequest class."""
    include_events: bool = Field(
        default=True,
        description="Whether to factor upcoming events into volatility/risk adjustment",
    )


# ── ADD to PredictionResponse ─────────────────────────────────────────────

class EventContext(BaseModel):
    """Nested event context block returned inside PredictionResponse."""
    # Earnings
    next_earnings_date: Optional[str] = None
    days_to_next_earnings: Optional[int] = None
    earnings_window: bool = False          # True → earnings within 7 days

    # FOMC
    next_fomc_date: Optional[str] = None
    days_to_next_fomc: Optional[int] = None
    fomc_window: bool = False

    # CPI
    next_cpi_date: Optional[str] = None
    days_to_next_cpi: Optional[int] = None
    cpi_window: bool = False

    # Combined volatility multiplier applied to confidence interval
    combined_vol_multiplier: float = 1.0


class PredictionResponseAdditions(BaseModel):
    """Copy this field into your existing PredictionResponse class."""
    event_context: Optional[EventContext] = None

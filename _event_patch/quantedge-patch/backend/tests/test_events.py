"""
Unit tests for event-aware forecasting.
Run: pytest backend/tests/test_events.py -v
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest

# Adjust import path to match your project
from backend.app.services.data_fetchers.events import (
    EARNINGS_WINDOW_DAYS,
    VOL_MULTIPLIER_EARNINGS_NEAR,
    VOL_MULTIPLIER_EARNINGS_SOON,
    _days_to,
    get_earnings_calendar,
    get_event_context,
    get_macro_events,
)
from backend.app.services.ml.prediction_patch import _apply_event_adjustments


# ── Helpers ────────────────────────────────────────────────────────────────

def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── _days_to ───────────────────────────────────────────────────────────────

def test_days_to_future():
    future = date.today() + timedelta(days=5)
    assert _days_to(future) == 5


def test_days_to_past_returns_none():
    past = date.today() - timedelta(days=1)
    assert _days_to(past) is None


def test_days_to_none_returns_none():
    assert _days_to(None) is None


# ── get_earnings_calendar ─────────────────────────────────────────────────

def test_earnings_in_window_raises_vol_multiplier():
    """If earnings is within EARNINGS_WINDOW_DAYS, vol multiplier must be >= NEAR."""
    near_date = date.today() + timedelta(days=3)

    with (
        patch(
            "backend.app.services.data_fetchers.events._fetch_earnings_finnhub",
            new=AsyncMock(return_value=near_date),
        ),
    ):
        result = run(get_earnings_calendar("AAPL"))

    assert result["earnings_window"] is True
    assert result["vol_multiplier"] == VOL_MULTIPLIER_EARNINGS_NEAR
    assert result["days_to_next_earnings"] == 3


def test_earnings_soon_but_not_in_window():
    soon_date = date.today() + timedelta(days=EARNINGS_WINDOW_DAYS + 3)

    with (
        patch(
            "backend.app.services.data_fetchers.events._fetch_earnings_finnhub",
            new=AsyncMock(return_value=soon_date),
        ),
    ):
        result = run(get_earnings_calendar("MSFT"))

    assert result["earnings_window"] is False
    assert result["vol_multiplier"] == VOL_MULTIPLIER_EARNINGS_SOON


def test_earnings_far_away_no_adjustment():
    far_date = date.today() + timedelta(days=60)

    with (
        patch(
            "backend.app.services.data_fetchers.events._fetch_earnings_finnhub",
            new=AsyncMock(return_value=far_date),
        ),
    ):
        result = run(get_earnings_calendar("GOOGL"))

    assert result["vol_multiplier"] == 1.0
    assert result["earnings_window"] is False


def test_earnings_api_failure_returns_safe_defaults():
    with (
        patch(
            "backend.app.services.data_fetchers.events._fetch_earnings_finnhub",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "backend.app.services.data_fetchers.events._fetch_earnings_yfinance",
            new=AsyncMock(return_value=None),
        ),
    ):
        result = run(get_earnings_calendar("TSLA"))

    assert result["next_earnings_date"] is None
    assert result["vol_multiplier"] == 1.0
    assert result["earnings_window"] is False


# ── get_macro_events ──────────────────────────────────────────────────────

def test_macro_events_returns_required_keys():
    result = get_macro_events()
    required = [
        "next_fomc_date", "days_to_next_fomc", "fomc_window", "fomc_vol_multiplier",
        "next_cpi_date", "days_to_next_cpi", "cpi_window", "cpi_vol_multiplier",
    ]
    for key in required:
        assert key in result, f"Missing key: {key}"


def test_macro_events_fomc_window_sets_multiplier():
    """If FOMC is within window, multiplier must be > 1."""
    from backend.app.services.data_fetchers import events as ev_module

    near_fomc = date.today() + timedelta(days=2)
    mock_cal = {
        "fomc": [near_fomc.isoformat()],
        "cpi": [],
    }

    with patch.object(ev_module, "_load_calendar", return_value=mock_cal):
        result = get_macro_events()

    assert result["fomc_window"] is True
    assert result["fomc_vol_multiplier"] > 1.0


# ── _apply_event_adjustments ──────────────────────────────────────────────

def test_event_adjustments_widens_confidence_interval():
    near_date = date.today() + timedelta(days=2)

    with (
        patch(
            "backend.app.services.data_fetchers.events._fetch_earnings_finnhub",
            new=AsyncMock(return_value=near_date),
        ),
        patch(
            "backend.app.services.data_fetchers.events.get_macro_events",
            return_value={
                "next_fomc_date": None, "days_to_next_fomc": None,
                "fomc_window": False, "fomc_vol_multiplier": 1.0,
                "next_cpi_date": None, "days_to_next_cpi": None,
                "cpi_window": False, "cpi_vol_multiplier": 1.0,
            },
        ),
    ):
        adj_low, adj_high, risk, ctx = run(
            _apply_event_adjustments(
                ticker="AAPL",
                include_events=True,
                predicted_price=150.0,
                confidence_low=145.0,   # range = 5
                confidence_high=155.0,  # range = 5
                risk_level="low",
            )
        )

    # Confidence interval must be wider
    assert adj_low < 145.0
    assert adj_high > 155.0

    # Risk must be floored to at least medium
    assert risk in ("medium", "high")


def test_event_adjustments_skipped_when_disabled():
    adj_low, adj_high, risk, ctx = run(
        _apply_event_adjustments(
            ticker="AAPL",
            include_events=False,
            predicted_price=150.0,
            confidence_low=145.0,
            confidence_high=155.0,
            risk_level="low",
        )
    )

    assert adj_low == 145.0
    assert adj_high == 155.0
    assert risk == "low"
    assert ctx == {}

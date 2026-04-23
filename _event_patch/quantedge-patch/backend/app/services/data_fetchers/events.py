"""
Event-aware data fetcher.
Fetches upcoming earnings (Finnhub → yfinance fallback) and macro events
(FOMC / CPI) from a static calendar JSON.

All public functions return plain dicts and never raise — graceful fallback
on any API failure so prediction continues to work.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants / thresholds (change here to tune behaviour)
# ---------------------------------------------------------------------------
EARNINGS_WINDOW_DAYS: int = 7          # <= N days → earnings_window = True
FOMC_WINDOW_DAYS: int = 5
CPI_WINDOW_DAYS: int = 5

VOL_MULTIPLIER_EARNINGS_NEAR: float = 1.5   # within EARNINGS_WINDOW_DAYS
VOL_MULTIPLIER_EARNINGS_SOON: float = 1.2   # within 2× EARNINGS_WINDOW_DAYS
VOL_MULTIPLIER_FOMC_NEAR: float = 1.3
VOL_MULTIPLIER_CPI_NEAR: float = 1.2

CALENDAR_PATH = Path(__file__).parent.parent.parent / "data" / "event_calendar.json"

FINNHUB_BASE = "https://finnhub.io/api/v1"
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")


# ---------------------------------------------------------------------------
# Earnings
# ---------------------------------------------------------------------------

def _days_to(target: date | None) -> int | None:
    if target is None:
        return None
    delta = (target - date.today()).days
    return delta if delta >= 0 else None


async def _fetch_earnings_finnhub(ticker: str) -> date | None:
    """Try Finnhub earnings calendar endpoint."""
    if not FINNHUB_API_KEY:
        return None
    today = date.today()
    to_date = today + timedelta(days=90)
    url = (
        f"{FINNHUB_BASE}/calendar/earnings"
        f"?from={today.isoformat()}&to={to_date.isoformat()}"
        f"&symbol={ticker}&token={FINNHUB_API_KEY}"
    )
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            entries = data.get("earningsCalendar", [])
            if not entries:
                return None
            # Take the closest future date
            dates = sorted(
                [
                    datetime.strptime(e["date"], "%Y-%m-%d").date()
                    for e in entries
                    if e.get("date")
                ]
            )
            future = [d for d in dates if d >= today]
            return future[0] if future else None
    except Exception as exc:
        logger.warning("Finnhub earnings fetch failed for %s: %s", ticker, exc)
        return None


async def _fetch_earnings_yfinance(ticker: str) -> date | None:
    """Fallback: yfinance calendar (sync → run in thread)."""
    try:
        import asyncio

        def _sync() -> date | None:
            import yfinance as yf  # type: ignore

            t = yf.Ticker(ticker)
            cal = t.calendar
            if cal is None:
                return None
            # cal is a DataFrame with index like 'Earnings Date'
            if hasattr(cal, "loc"):
                try:
                    ed = cal.loc["Earnings Date"]
                    if hasattr(ed, "iloc"):
                        ed = ed.iloc[0]
                    return pd_ts_to_date(ed)
                except (KeyError, IndexError):
                    pass
            return None

        return await asyncio.get_event_loop().run_in_executor(None, _sync)
    except Exception as exc:
        logger.warning("yfinance earnings fetch failed for %s: %s", ticker, exc)
        return None


def pd_ts_to_date(ts: Any) -> date | None:
    try:
        return ts.date() if hasattr(ts, "date") else date.fromisoformat(str(ts)[:10])
    except Exception:
        return None


async def get_earnings_calendar(ticker: str) -> dict[str, Any]:
    """
    Returns:
        {
          "next_earnings_date": "YYYY-MM-DD" | None,
          "days_to_next_earnings": int | None,
          "earnings_window": bool,
          "vol_multiplier": float,
        }
    """
    next_date = await _fetch_earnings_finnhub(ticker)
    if next_date is None:
        next_date = await _fetch_earnings_yfinance(ticker)

    days = _days_to(next_date)
    in_window = days is not None and days <= EARNINGS_WINDOW_DAYS
    soon = days is not None and days <= EARNINGS_WINDOW_DAYS * 2

    if in_window:
        vol_mult = VOL_MULTIPLIER_EARNINGS_NEAR
    elif soon:
        vol_mult = VOL_MULTIPLIER_EARNINGS_SOON
    else:
        vol_mult = 1.0

    return {
        "next_earnings_date": next_date.isoformat() if next_date else None,
        "days_to_next_earnings": days,
        "earnings_window": in_window,
        "vol_multiplier": vol_mult,
    }


# ---------------------------------------------------------------------------
# Macro events (FOMC / CPI) — static calendar
# ---------------------------------------------------------------------------

def _load_calendar() -> dict[str, list[str]]:
    try:
        with open(CALENDAR_PATH) as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("Could not load event_calendar.json: %s", exc)
        return {}


def _next_macro_date(dates: list[str]) -> date | None:
    today = date.today()
    future: list[date] = []
    for ds in dates:
        try:
            d = date.fromisoformat(ds)
            if d >= today:
                future.append(d)
        except ValueError:
            pass
    return min(future) if future else None


def get_macro_events() -> dict[str, Any]:
    """
    Returns:
        {
          "next_fomc_date": str | None,
          "days_to_next_fomc": int | None,
          "fomc_window": bool,
          "fomc_vol_multiplier": float,
          "next_cpi_date": str | None,
          "days_to_next_cpi": int | None,
          "cpi_window": bool,
          "cpi_vol_multiplier": float,
        }
    """
    cal = _load_calendar()

    fomc_date = _next_macro_date(cal.get("fomc", []))
    cpi_date = _next_macro_date(cal.get("cpi", []))

    fomc_days = _days_to(fomc_date)
    cpi_days = _days_to(cpi_date)

    fomc_window = fomc_days is not None and fomc_days <= FOMC_WINDOW_DAYS
    cpi_window = cpi_days is not None and cpi_days <= CPI_WINDOW_DAYS

    return {
        "next_fomc_date": fomc_date.isoformat() if fomc_date else None,
        "days_to_next_fomc": fomc_days,
        "fomc_window": fomc_window,
        "fomc_vol_multiplier": VOL_MULTIPLIER_FOMC_NEAR if fomc_window else 1.0,
        "next_cpi_date": cpi_date.isoformat() if cpi_date else None,
        "days_to_next_cpi": cpi_days,
        "cpi_window": cpi_window,
        "cpi_vol_multiplier": VOL_MULTIPLIER_CPI_NEAR if cpi_window else 1.0,
    }


# ---------------------------------------------------------------------------
# Aggregate: single call that merges earnings + macro
# ---------------------------------------------------------------------------

async def get_event_context(ticker: str) -> dict[str, Any]:
    """
    Full event context dict used by the prediction pipeline.
    Never raises.
    """
    try:
        earnings = await get_earnings_calendar(ticker)
    except Exception as exc:
        logger.error("get_earnings_calendar error: %s", exc)
        earnings = {
            "next_earnings_date": None,
            "days_to_next_earnings": None,
            "earnings_window": False,
            "vol_multiplier": 1.0,
        }

    try:
        macro = get_macro_events()
    except Exception as exc:
        logger.error("get_macro_events error: %s", exc)
        macro = {
            "next_fomc_date": None, "days_to_next_fomc": None,
            "fomc_window": False, "fomc_vol_multiplier": 1.0,
            "next_cpi_date": None, "days_to_next_cpi": None,
            "cpi_window": False, "cpi_vol_multiplier": 1.0,
        }

    # Overall vol multiplier = product of active event multipliers
    combined_vol_mult = (
        earnings["vol_multiplier"]
        * macro["fomc_vol_multiplier"]
        * macro["cpi_vol_multiplier"]
    )

    return {
        # Earnings
        "next_earnings_date": earnings["next_earnings_date"],
        "days_to_next_earnings": earnings["days_to_next_earnings"],
        "earnings_window": earnings["earnings_window"],
        # FOMC
        "next_fomc_date": macro["next_fomc_date"],
        "days_to_next_fomc": macro["days_to_next_fomc"],
        "fomc_window": macro["fomc_window"],
        # CPI
        "next_cpi_date": macro["next_cpi_date"],
        "days_to_next_cpi": macro["days_to_next_cpi"],
        "cpi_window": macro["cpi_window"],
        # Combined
        "combined_vol_multiplier": round(combined_vol_mult, 3),
    }

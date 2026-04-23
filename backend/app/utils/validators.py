"""
QuantEdge AI — Girdi Doğrulama Yardımcıları
=============================================
API ve servis katmanı için yeniden kullanılabilir validator'lar.
"""

import re
from datetime import datetime, date
from typing import List, Optional

from fastapi import HTTPException


# ----------------------------------------------------------
# Ticker Validator
# ----------------------------------------------------------

# Geçerli ticker formatı: 1-5 büyük harf, opsiyonel nokta+harf (BRK.B gibi)
_TICKER_RE = re.compile(r'^[A-Z]{1,5}(\.[A-Z]{1,2})?$')

KNOWN_INVALID = {"TEST", "FAKE", "XXXX", "NULL", "NONE"}


def validate_ticker(ticker: str, raise_on_invalid: bool = True) -> str:
    """
    Ticker sembolünü doğrular ve normalize eder.

    Args:
        ticker           : Ham ticker string
        raise_on_invalid : True → HTTPException fırlatır, False → None döner

    Returns:
        Normalize edilmiş büyük harfli ticker

    Raises:
        HTTPException 400: Geçersiz format
    """
    if not ticker:
        if raise_on_invalid:
            raise HTTPException(status_code=400, detail="Ticker boş olamaz.")
        return None

    normalized = ticker.upper().strip()

    if normalized in KNOWN_INVALID:
        if raise_on_invalid:
            raise HTTPException(status_code=400, detail=f"Geçersiz ticker: {ticker}")
        return None

    if not _TICKER_RE.match(normalized):
        if raise_on_invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Geçersiz ticker formatı: '{ticker}'. 1-5 büyük harf bekleniyor (örn: AAPL, BRK.B)."
            )
        return None

    return normalized


def validate_ticker_list(tickers: List[str], max_count: int = 10) -> List[str]:
    """
    Ticker listesini doğrular.

    Args:
        tickers  : Ticker listesi
        max_count: Maksimum izin verilen sayı

    Returns:
        Normalize edilmiş geçerli ticker listesi
    """
    if not tickers:
        raise HTTPException(status_code=400, detail="Ticker listesi boş olamaz.")

    if len(tickers) > max_count:
        raise HTTPException(
            status_code=400,
            detail=f"En fazla {max_count} ticker sorgulanabilir. {len(tickers)} verildi."
        )

    validated = []
    for t in tickers:
        v = validate_ticker(t, raise_on_invalid=False)
        if v:
            validated.append(v)

    if not validated:
        raise HTTPException(status_code=400, detail="Geçerli ticker bulunamadı.")

    return list(dict.fromkeys(validated))   # Tekrarları kaldır, sırayı koru


# ----------------------------------------------------------
# Timeframe Validator
# ----------------------------------------------------------

VALID_TIMEFRAMES = {"1d", "1w", "1mo", "3mo", "1y"}
VALID_CHART_TIMEFRAMES = {"1d", "1h", "5m", "1w", "1mo"}


def validate_timeframe(
    timeframe: str,
    allowed: Optional[set] = None,
) -> str:
    """
    Zaman dilimini doğrular.

    Args:
        timeframe: Zaman dilimi string
        allowed  : İzin verilen değerler seti (None → VALID_TIMEFRAMES)

    Returns:
        Doğrulanmış timeframe string

    Raises:
        HTTPException 400: Geçersiz timeframe
    """
    valid = allowed or VALID_TIMEFRAMES
    if timeframe not in valid:
        raise HTTPException(
            status_code=400,
            detail=f"Geçersiz zaman dilimi: '{timeframe}'. İzin verilenler: {sorted(valid)}"
        )
    return timeframe


# ----------------------------------------------------------
# Tarih Validator
# ----------------------------------------------------------

def validate_date_range(
    start_date: Optional[str],
    end_date: Optional[str],
    max_days: int = 3650,   # ~10 yıl
) -> tuple:
    """
    Tarih aralığını doğrular.

    Args:
        start_date: 'YYYY-MM-DD' formatında başlangıç tarihi
        end_date  : 'YYYY-MM-DD' formatında bitiş tarihi
        max_days  : Maksimum aralık (gün)

    Returns:
        (start: date, end: date) tuple

    Raises:
        HTTPException 400: Geçersiz tarih
    """
    today = date.today()

    # Bitiş tarihi (varsayılan: bugün)
    if end_date:
        try:
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Geçersiz bitiş tarihi: '{end_date}'. Format: YYYY-MM-DD"
            )
        if end > today:
            raise HTTPException(status_code=400, detail="Bitiş tarihi bugünden sonra olamaz.")
    else:
        end = today

    # Başlangıç tarihi (varsayılan: 1 yıl önce)
    if start_date:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Geçersiz başlangıç tarihi: '{start_date}'. Format: YYYY-MM-DD"
            )
    else:
        from datetime import timedelta
        start = end - timedelta(days=365)

    if start >= end:
        raise HTTPException(
            status_code=400,
            detail="Başlangıç tarihi bitiş tarihinden önce olmalıdır."
        )

    delta = (end - start).days
    if delta > max_days:
        raise HTTPException(
            status_code=400,
            detail=f"Tarih aralığı çok büyük: {delta} gün. Maksimum: {max_days} gün."
        )

    return start, end


# ----------------------------------------------------------
# Limit Validator
# ----------------------------------------------------------

def validate_limit(limit: int, min_val: int = 1, max_val: int = 1000) -> int:
    """Bar/kayıt sayısı limitini doğrular."""
    if not (min_val <= limit <= max_val):
        raise HTTPException(
            status_code=400,
            detail=f"Limit {min_val} ile {max_val} arasında olmalıdır. Verilen: {limit}"
        )
    return limit


# ----------------------------------------------------------
# Confidence Validator
# ----------------------------------------------------------

def validate_confidence(value: float) -> float:
    """Güven skorunun 0-1 arasında olduğunu doğrular."""
    if not (0.0 <= value <= 1.0):
        raise HTTPException(
            status_code=400,
            detail=f"Güven skoru 0.0 ile 1.0 arasında olmalıdır. Verilen: {value}"
        )
    return value

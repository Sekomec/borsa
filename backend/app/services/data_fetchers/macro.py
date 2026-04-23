"""
QuantEdge AI — Makroekonomik Veri Çekme Modülü
================================================
Kaynaklar:
  1. FRED API (Federal Reserve Economic Data) — FED faiz, TÜFE, DXY, VIX, Hazine
  2. BLS API  (Bureau of Labor Statistics)    — NFP, İşsizlik oranı, PPI
  3. Treasury API                              — 10 yıllık tahvil getirisi
  4. Yahoo Finance                             — VIX, DXY (yedek)

FRED Serileri:
  DFF       → FED Funds Rate (gecelik)
  T10Y2Y    → 10Y-2Y Yield Spread (Resesyon göstergesi)
  DTWEXBGS  → USD Broad Index (DXY benzeri)
  VIXCLS    → CBOE VIX
  CPIAUCSL  → TÜFE (Tüketici Fiyat Endeksi)
  PPIACO    → ÜFE (Üretici Fiyat Endeksi)
  UNRATE    → İşsizlik Oranı
  GS10      → 10 Yıllık Hazine Getirisi
  GDP       → GSYİH (Çeyreklik)
  M2SL      → M2 Para Arzı
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import aiohttp
import structlog

from app.core.config import settings
from app.core.cache import cache_manager, CacheNamespace
from app.utils.retry import async_retry, fred_limiter

logger = structlog.get_logger()


# ----------------------------------------------------------
# FRED API FETCHER
# ----------------------------------------------------------

class FREDFetcher:
    """
    Federal Reserve Economic Data (FRED) API istemcisi.

    800,000+ ekonomik zaman serisi.
    Ücretsiz API — https://fred.stlouisfed.org/docs/api/api_key.html
    """

    BASE_URL = "https://api.stlouisfed.org/fred"

    # İzlenen FRED seri kodları ve açıklamaları
    SERIES_CONFIG = {
        "DFF": {
            "name": "FED Funds Rate",
            "unit": "%",
            "description": "Federal Reserve gecelik faiz oranı",
        },
        "GS10": {
            "name": "10-Year Treasury Yield",
            "unit": "%",
            "description": "ABD 10 yıllık Hazine tahvil getirisi",
        },
        "GS2": {
            "name": "2-Year Treasury Yield",
            "unit": "%",
            "description": "ABD 2 yıllık Hazine tahvil getirisi",
        },
        "T10Y2Y": {
            "name": "Yield Curve Spread (10Y-2Y)",
            "unit": "%",
            "description": "Getiri eğrisi yayılımı — negatif = resesyon sinyali",
        },
        "VIXCLS": {
            "name": "VIX (CBOE Volatility Index)",
            "unit": "index",
            "description": "Piyasa korku endeksi",
        },
        "DTWEXBGS": {
            "name": "US Dollar Index",
            "unit": "index",
            "description": "ABD Dolar geniş endeksi (DXY benzeri)",
        },
        "CPIAUCSL": {
            "name": "CPI (All Urban Consumers)",
            "unit": "index",
            "description": "Tüketici fiyat endeksi",
        },
        "PPIACO": {
            "name": "PPI (All Commodities)",
            "unit": "index",
            "description": "Üretici fiyat endeksi",
        },
        "UNRATE": {
            "name": "Unemployment Rate",
            "unit": "%",
            "description": "ABD İşsizlik oranı",
        },
        "PAYEMS": {
            "name": "Nonfarm Payrolls (NFP)",
            "unit": "thousands",
            "description": "Tarımdışı istihdam",
        },
        "GDP": {
            "name": "US GDP",
            "unit": "billions USD",
            "description": "GSYİH (çeyreklik, milyar $)",
        },
        "M2SL": {
            "name": "M2 Money Supply",
            "unit": "billions USD",
            "description": "M2 para arzı",
        },
        "BAMLH0A0HYM2": {
            "name": "High Yield Spread",
            "unit": "%",
            "description": "Yüksek getirili tahvil spreadi (kredi riski göstergesi)",
        },
        "MORTGAGE30US": {
            "name": "30-Year Mortgage Rate",
            "unit": "%",
            "description": "30 yıllık mortgage faiz oranı",
        },
    }

    def __init__(self):
        self.api_key = settings.FRED_API_KEY

    @async_retry(max_attempts=3, delay=2.0)
    async def get_series(
        self,
        series_id: str,
        limit: int = 100,
        start_date: Optional[str] = None,
    ) -> Optional[List[Dict]]:
        """
        FRED'den belirtilen ekonomik zaman serisini çeker.

        Args:
            series_id  : FRED seri kodu (DFF, VIXCLS vb.)
            limit      : Maksimum gözlem sayısı
            start_date : 'YYYY-MM-DD' formatında başlangıç tarihi

        Returns:
            [{'date': '2024-01-01', 'value': 5.33, 'series_id': 'DFF'}]
        """
        if not self.api_key:
            raise ValueError("FRED_API_KEY tanımlı değil.")

        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": limit,
        }

        if start_date:
            params["observation_start"] = start_date

        url = f"{self.BASE_URL}/series/observations"

        async with fred_limiter:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 429:
                        raise Exception("FRED API rate limit aşıldı.")
                    if resp.status != 200:
                        raise Exception(f"FRED API HTTP {resp.status}")
                    data = await resp.json()

        observations = data.get("observations", [])
        series_info = self.SERIES_CONFIG.get(series_id, {})

        results = []
        for obs in observations:
            val_str = obs.get("value", ".")
            if val_str == ".":  # FRED'de eksik veri "." ile gösterilir
                continue
            try:
                results.append({
                    "date": obs["date"],
                    "value": float(val_str),
                    "series_id": series_id,
                    "series_name": series_info.get("name", series_id),
                    "unit": series_info.get("unit"),
                })
            except ValueError:
                continue

        return sorted(results, key=lambda x: x["date"])

    @async_retry(max_attempts=3, delay=2.0)
    async def get_latest_value(self, series_id: str) -> Optional[float]:
        """Belirtilen serinin en güncel değerini döndürür."""
        data = await self.get_series(series_id, limit=1)
        if data:
            return data[-1]["value"]
        return None

    async def get_macro_snapshot(self) -> Dict:
        """
        Tüm kritik makro göstergelerinin anlık görüntüsünü çeker.
        Paralel API çağrıları ile hızlandırılmış.
        """
        cache_key = "macro:snapshot"
        cached = await cache_manager.get(CacheNamespace.MACRO, cache_key)
        if cached:
            return cached

        # Tüm serileri paralel çek
        series_ids = list(self.SERIES_CONFIG.keys())
        tasks = {sid: self.get_latest_value(sid) for sid in series_ids}

        logger.info("Makro göstergeler çekiliyor...", count=len(series_ids))

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        values = {}
        for sid, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                logger.warning("Makro seri alınamadı.", series=sid, error=str(result))
                values[sid] = None
            else:
                values[sid] = result

        # Temiz snapshot oluştur
        snapshot = {
            "fed_rate": values.get("DFF"),
            "us_10y_yield": values.get("GS10"),
            "us_2y_yield": values.get("GS2"),
            "yield_curve_spread": values.get("T10Y2Y"),
            "vix": values.get("VIXCLS"),
            "dxy": values.get("DTWEXBGS"),
            "cpi_level": values.get("CPIAUCSL"),
            "ppi_level": values.get("PPIACO"),
            "unemployment_rate": values.get("UNRATE"),
            "nfp_thousands": values.get("PAYEMS"),
            "gdp_billions": values.get("GDP"),
            "m2_billions": values.get("M2SL"),
            "high_yield_spread": values.get("BAMLH0A0HYM2"),
            "mortgage_rate_30y": values.get("MORTGAGE30US"),
            "last_updated": datetime.utcnow().isoformat(),
            "source": "FRED",
        }

        # Türetilmiş makro metrikler
        snapshot["macro_risk_score"] = self._calculate_macro_risk(snapshot)
        snapshot["macro_regime"] = self._identify_macro_regime(snapshot)

        # 6 saatlik cache (günde birkaç kez yeterli)
        await cache_manager.set(CacheNamespace.MACRO, cache_key, snapshot, ttl=21600)
        return snapshot

    async def get_historical_macro(
        self,
        series_id: str,
        years: int = 5,
    ) -> Optional[List[Dict]]:
        """Belirtilen sürece ait tarihsel makro veriyi çeker."""
        start_date = (datetime.utcnow() - timedelta(days=365 * years)).strftime("%Y-%m-%d")
        return await self.get_series(series_id, limit=years * 365, start_date=start_date)

    def _calculate_macro_risk(self, snapshot: Dict) -> float:
        """
        0 (düşük risk) ile 100 (yüksek risk) arası makro risk skoru.

        Faktörler:
        - VIX (yüksek = yüksek risk)
        - Yield Curve (negatif = resesyon riski)
        - FED Faizi (yüksek = kısıtlayıcı)
        - High Yield Spread (yüksek = kredi riski)
        """
        score = 30.0  # Temel risk seviyesi

        vix = snapshot.get("vix")
        if vix is not None:
            if vix > 40:
                score += 30
            elif vix > 25:
                score += 15
            elif vix > 20:
                score += 5
            elif vix < 15:
                score -= 5

        ycs = snapshot.get("yield_curve_spread")
        if ycs is not None:
            if ycs < -0.5:
                score += 25   # Güçlü inversiyon — ciddi resesyon sinyali
            elif ycs < 0:
                score += 12   # Hafif inversiyon
            elif ycs > 1.5:
                score -= 5    # Sağlıklı eğri

        fed_rate = snapshot.get("fed_rate")
        if fed_rate is not None:
            if fed_rate > 5:
                score += 10   # Kısıtlayıcı para politikası
            elif fed_rate > 4:
                score += 5

        hy_spread = snapshot.get("high_yield_spread")
        if hy_spread is not None:
            if hy_spread > 600:  # bps
                score += 20   # Yüksek kredi riski
            elif hy_spread > 400:
                score += 10

        return round(max(0, min(100, score)), 2)

    def _identify_macro_regime(self, snapshot: Dict) -> str:
        """
        Mevcut makro rejimi tanımlar.
        Tahmin modeli için bağlam sağlar.
        """
        vix = snapshot.get("vix", 20)
        ycs = snapshot.get("yield_curve_spread", 1.0)
        fed_rate = snapshot.get("fed_rate", 3.0)
        risk_score = snapshot.get("macro_risk_score", 50)

        if risk_score > 70:
            return "CRISIS"           # Kriz modu (VIX>40, inversiyon)
        elif risk_score > 55:
            return "RISK_OFF"         # Risk kaçışı
        elif risk_score < 30 and ycs > 0.5 and vix < 18:
            return "GOLDILOCKS"       # İdeal büyüme ortamı
        elif fed_rate > 4.5 and vix < 22:
            return "TIGHTENING"       # Faiz artırım dönemi
        elif fed_rate < 2.0:
            return "EASING"           # Faiz indirim/teşvik dönemi
        else:
            return "NEUTRAL"          # Normal piyasa koşulları


# ----------------------------------------------------------
# BLS (Bureau of Labor Statistics) FETCHER
# ----------------------------------------------------------

class BLSFetcher:
    """
    BLS API istemcisi.
    Resmi istihdam istatistikleri: NFP, işsizlik, CPI detayları.

    Ücretsiz: https://www.bls.gov/developers/
    """

    BASE_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

    # BLS Seri Kodları
    SERIES = {
        "CES0000000001": "Total Nonfarm Payrolls",
        "LNS14000000": "Unemployment Rate",
        "CUUR0000SA0": "CPI-U All Items",
        "PCU": "PPI",
    }

    def __init__(self):
        self.api_key = settings.BLS_API_KEY

    @async_retry(max_attempts=3, delay=3.0)
    async def get_series_data(
        self,
        series_ids: List[str],
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
    ) -> Optional[Dict]:
        """BLS'den birden fazla seriyi çeker."""
        now = datetime.utcnow()
        payload = {
            "seriesid": series_ids,
            "startyear": str(start_year or now.year - 2),
            "endyear": str(end_year or now.year),
        }

        if self.api_key:
            payload["registrationkey"] = self.api_key

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.BASE_URL,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                if resp.status != 200:
                    raise Exception(f"BLS API HTTP {resp.status}")
                data = await resp.json()

        if data.get("status") != "REQUEST_SUCCEEDED":
            raise Exception(f"BLS API hatası: {data.get('message', 'Bilinmeyen hata')}")

        results = {}
        for series in data.get("Results", {}).get("series", []):
            sid = series.get("seriesID")
            observations = [
                {
                    "year": int(obs["year"]),
                    "period": obs["period"],
                    "value": float(obs["value"]),
                    "footnotes": obs.get("footnotes", []),
                }
                for obs in series.get("data", [])
                if obs.get("value", "-") != "-"
            ]
            results[sid] = sorted(observations, key=lambda x: (x["year"], x["period"]))

        return results


# ----------------------------------------------------------
# ANA MAKRO SERVİSİ
# ----------------------------------------------------------

class MacroDataService:
    """
    FRED + BLS makro verilerini birleştiren ana servis.
    """

    def __init__(self):
        self.fred = FREDFetcher()
        self.bls = BLSFetcher()

    async def get_full_macro_context(self) -> Dict:
        """
        Tahmin motoru için tam makro bağlam paketi.
        Model girişi olarak kullanılır.
        """
        cache_key = "macro:full_context"
        cached = await cache_manager.get(CacheNamespace.MACRO, cache_key)
        if cached:
            return cached

        # FRED anlık snapshot
        snapshot = await self.fred.get_macro_snapshot()

        # FRED tarihsel (YoY değişimler için)
        historical_tasks = [
            self.fred.get_series("CPIAUCSL", limit=24),   # 2 yıllık CPI
            self.fred.get_series("DFF", limit=24),         # 2 yıllık FED Faiz
            self.fred.get_series("VIXCLS", limit=252),     # 1 yıllık VIX
        ]
        cpi_hist, fed_hist, vix_hist = await asyncio.gather(
            *historical_tasks, return_exceptions=True
        )

        # YoY enflasyon hesapla
        cpi_yoy = None
        if isinstance(cpi_hist, list) and len(cpi_hist) >= 13:
            try:
                current_cpi = cpi_hist[-1]["value"]
                year_ago_cpi = cpi_hist[-13]["value"]
                cpi_yoy = ((current_cpi - year_ago_cpi) / year_ago_cpi) * 100
            except (IndexError, KeyError, ZeroDivisionError):
                pass

        # VIX 30 günlük ortalama
        vix_30d_avg = None
        if isinstance(vix_hist, list) and len(vix_hist) >= 30:
            try:
                vix_30d_avg = sum(v["value"] for v in vix_hist[-30:]) / 30
            except Exception:
                pass

        context = {
            **snapshot,
            "cpi_yoy_pct": round(cpi_yoy, 2) if cpi_yoy else None,
            "vix_30d_avg": round(vix_30d_avg, 2) if vix_30d_avg else None,
            "historical_available": {
                "cpi": not isinstance(cpi_hist, Exception),
                "fed_rate": not isinstance(fed_hist, Exception),
                "vix": not isinstance(vix_hist, Exception),
            },
        }

        await cache_manager.set(CacheNamespace.MACRO, cache_key, context, ttl=3600 * 6)
        return context

    async def get_macro_feature_vector(self) -> Dict[str, float]:
        """
        ML modeli için normalize edilmiş makro feature vektörü.
        Tüm değerler 0-1 arasına normalize edilir.
        """
        context = await self.get_full_macro_context()

        def safe_normalize(value, min_val, max_val):
            if value is None:
                return 0.5  # Eksik veri için nötr değer
            return max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))

        return {
            "macro_vix_norm": safe_normalize(context.get("vix"), 10, 80),
            "macro_fed_rate_norm": safe_normalize(context.get("fed_rate"), 0, 7),
            "macro_10y_yield_norm": safe_normalize(context.get("us_10y_yield"), 0.5, 6),
            "macro_yield_curve_norm": safe_normalize(context.get("yield_curve_spread"), -2, 3),
            "macro_unemployment_norm": safe_normalize(context.get("unemployment_rate"), 3, 12),
            "macro_risk_score_norm": safe_normalize(context.get("macro_risk_score"), 0, 100),
            "macro_cpi_yoy_norm": safe_normalize(context.get("cpi_yoy_pct"), 0, 10),
            "macro_hy_spread_norm": safe_normalize(context.get("high_yield_spread"), 200, 1000),
        }


# Singleton
macro_service = MacroDataService()

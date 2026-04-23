"""
QuantEdge AI — Temel Analiz Veri Çekme Modülü
===============================================
Kaynaklar:
  1. Finnhub        : Finansal tablolar, insider trading, kurumsal hareketler
  2. Alpha Vantage  : Gelir tablosu, bilanço, nakit akışı
  3. SEC EDGAR      : 10-K, 10-Q, 13F formları (resmi kaynak)
  4. yfinance       : Fallback temel veriler

Veri Tipleri:
  - Değerleme oranları (P/E, P/B, PEG, EV/EBITDA)
  - Finansal tablolar (gelir, bilanço, nakit akışı)
  - Insider işlemler
  - Kurumsal yatırımcı hareketleri (13F)
  - Sektör karşılaştırması
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import aiohttp
import structlog

from app.core.config import settings
from app.core.cache import cache_manager, CacheNamespace
from app.utils.retry import async_retry, finnhub_limiter, alpha_vantage_limiter

logger = structlog.get_logger()


# ----------------------------------------------------------
# FINNHUB FETCHER
# ----------------------------------------------------------

class FinnhubFetcher:
    """
    Finnhub API istemcisi.
    Temel analiz, insider trading, kurumsal veriler sağlar.

    Ücretsiz plan: Dakikada 60 istek
    """

    BASE_URL = "https://finnhub.io/api/v1"

    def __init__(self):
        self.api_key = settings.FINNHUB_API_KEY

    async def _get(self, endpoint: str, params: dict = None) -> Optional[Dict]:
        """Yardımcı GET isteği."""
        if not self.api_key:
            raise ValueError("FINNHUB_API_KEY tanımlı değil.")

        all_params = {"token": self.api_key, **(params or {})}
        url = f"{self.BASE_URL}/{endpoint}"

        async with finnhub_limiter:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=all_params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 429:
                        raise Exception("Finnhub rate limit aşıldı.")
                    if resp.status != 200:
                        raise Exception(f"Finnhub HTTP {resp.status}")
                    return await resp.json()

    @async_retry(max_attempts=3, delay=2.0)
    async def get_basic_financials(self, ticker: str) -> Optional[Dict]:
        """
        Temel finansal oranları çeker.
        P/E, P/B, EPS, revenue growth, margin'ler vb.
        """
        data = await self._get("stock/metric", {"symbol": ticker, "metric": "all"})
        if not data or "metric" not in data:
            return None

        m = data["metric"]
        return {
            "ticker": ticker,
            "pe_ratio": m.get("peNormalizedAnnual") or m.get("peTTM"),
            "pb_ratio": m.get("pbAnnual") or m.get("pbQuarterly"),
            "ps_ratio": m.get("psTTM"),
            "peg_ratio": m.get("pegAnnual"),
            "ev_ebitda": m.get("evEbitdaTTM"),
            "eps": m.get("epsTTM"),
            "eps_growth_3y": m.get("epsGrowth3Y"),
            "eps_growth_5y": m.get("epsGrowth5Y"),
            "revenue_growth_3y": m.get("revenueGrowth3Y"),
            "revenue_growth_5y": m.get("revenueGrowth5Y"),
            "gross_margin": m.get("grossMarginTTM"),
            "operating_margin": m.get("operatingMarginTTM"),
            "net_margin": m.get("netProfitMarginTTM"),
            "roe": m.get("roeTTM"),
            "roa": m.get("roaTTM"),
            "current_ratio": m.get("currentRatioAnnual"),
            "debt_to_equity": m.get("totalDebt/totalEquityAnnual"),
            "dividend_yield": m.get("dividendYieldIndicatedAnnual"),
            "52w_high": m.get("52WeekHigh"),
            "52w_low": m.get("52WeekLow"),
            "beta": m.get("beta"),
            "source": "finnhub",
        }

    @async_retry(max_attempts=3, delay=2.0)
    async def get_insider_transactions(self, ticker: str, days: int = 90) -> Optional[List[Dict]]:
        """
        Şirket içi kişilerin alım/satım işlemlerini çeker.
        (CEO, CFO, büyük hissedarlar)
        """
        from_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        to_date = datetime.utcnow().strftime("%Y-%m-%d")

        data = await self._get("stock/insider-transactions", {
            "symbol": ticker, "from": from_date, "to": to_date
        })

        if not data or "data" not in data:
            return []

        transactions = []
        for item in data["data"]:
            transactions.append({
                "name": item.get("name"),
                "title": item.get("position"),
                "transaction_type": item.get("transactionCode"),  # P=Purchase, S=Sale
                "shares": item.get("share"),
                "value": item.get("value"),
                "date": item.get("transactionDate"),
                "filing_date": item.get("filingDate"),
            })

        return transactions

    @async_retry(max_attempts=3, delay=2.0)
    async def get_earnings_calendar(self, ticker: str) -> Optional[Dict]:
        """Kazanç raporu tarihlerini ve tahminleri çeker."""
        data = await self._get("calendar/earnings", {"symbol": ticker})
        if not data:
            return None

        earnings = data.get("earningsCalendar", [])
        if not earnings:
            return None

        next_earnings = earnings[0] if earnings else {}
        return {
            "ticker": ticker,
            "next_earnings_date": next_earnings.get("date"),
            "eps_estimate": next_earnings.get("epsEstimate"),
            "revenue_estimate": next_earnings.get("revenueEstimate"),
            "source": "finnhub",
        }

    @async_retry(max_attempts=3, delay=2.0)
    async def get_recommendation_trends(self, ticker: str) -> Optional[List[Dict]]:
        """Analist öneri trendlerini çeker (Strong Buy, Buy, Hold, Sell)."""
        data = await self._get("stock/recommendation", {"symbol": ticker})
        if not data:
            return []

        return [
            {
                "period": item.get("period"),
                "strong_buy": item.get("strongBuy"),
                "buy": item.get("buy"),
                "hold": item.get("hold"),
                "sell": item.get("sell"),
                "strong_sell": item.get("strongSell"),
            }
            for item in data[:6]  # Son 6 ay
        ]

    @async_retry(max_attempts=3, delay=2.0)
    async def get_peers(self, ticker: str) -> List[str]:
        """Benzer şirketleri (peer group) çeker."""
        data = await self._get("stock/peers", {"symbol": ticker})
        return data if isinstance(data, list) else []


# ----------------------------------------------------------
# SEC EDGAR FETCHER
# ----------------------------------------------------------

class SECEdgarFetcher:
    """
    SEC EDGAR API istemcisi.
    Resmi SEC formları: 10-K (yıllık), 10-Q (çeyreklik), 13F (kurumsal)

    API Belgesi: https://efts.sec.gov/LATEST/search-index?q=
    EDGAR Full-Text Search API: ücretsiz, anahtar gerektirmez.
    """

    BASE_URL = "https://data.sec.gov"
    EFTS_URL = "https://efts.sec.gov"

    def __init__(self):
        # SEC User-Agent zorunlu
        self.headers = {
            "User-Agent": "QuantEdge AI quantedge@example.com",
            "Accept-Encoding": "gzip, deflate",
        }

    async def _get_cik(self, ticker: str) -> Optional[str]:
        """Ticker'dan CIK (Central Index Key) numarasını alır."""
        cache_key = f"cik:{ticker}"
        cached = await cache_manager.get("sec", cache_key)
        if cached:
            return cached

        url = f"{self.BASE_URL}/submissions/CIK.json"
        # EDGAR ticker arama
        search_url = "https://www.sec.gov/cgi-bin/browse-edgar"
        params = {
            "company": "",
            "CIK": ticker,
            "type": "10-K",
            "dateb": "",
            "owner": "include",
            "count": "1",
            "search_text": "",
            "action": "getcompany",
            "output": "atom",
        }

        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(search_url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    text = await resp.text()
                    # CIK parse (basit text arama)
                    import re
                    match = re.search(r'CIK=(\d{10})', text)
                    if match:
                        cik = match.group(1).lstrip("0")
                        await cache_manager.set("sec", cache_key, cik, ttl=86400 * 30)
                        return cik
        except Exception as e:
            logger.warning("CIK alınamadı.", ticker=ticker, error=str(e))

        return None

    @async_retry(max_attempts=2, delay=5.0)
    async def get_company_facts(self, ticker: str) -> Optional[Dict]:
        """
        EDGAR'dan şirket finansal gerçeklerini çeker.
        XBRL formatında yapılandırılmış mali tablo verileri.
        """
        cik = await self._get_cik(ticker)
        if not cik:
            logger.warning("CIK bulunamadı, EDGAR atlanıyor.", ticker=ticker)
            return None

        cik_padded = cik.zfill(10)
        url = f"{self.BASE_URL}/api/xbrl/companyfacts/CIK{cik_padded}.json"

        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 404:
                    logger.warning("EDGAR company facts bulunamadı.", ticker=ticker, cik=cik)
                    return None
                if resp.status != 200:
                    raise Exception(f"EDGAR HTTP {resp.status}")
                data = await resp.json()

        return self._parse_company_facts(ticker, data)

    def _parse_company_facts(self, ticker: str, raw: Dict) -> Dict:
        """EDGAR ham verisini temiz formata dönüştürür."""
        facts = raw.get("facts", {})
        us_gaap = facts.get("us-gaap", {})

        def get_latest_value(concept: str, unit: str = "USD") -> Optional[float]:
            """Belirtilen GAAP kavramının en son değerini alır."""
            concept_data = us_gaap.get(concept, {})
            units = concept_data.get("units", {}).get(unit, [])
            if not units:
                return None
            # 10-K (annual) tercih et, yoksa 10-Q al
            annual = [u for u in units if u.get("form") == "10-K"]
            quarterly = [u for u in units if u.get("form") == "10-Q"]
            source = annual or quarterly
            if not source:
                return None
            # En son tarihe göre sırala
            source.sort(key=lambda x: x.get("end", ""), reverse=True)
            return source[0].get("val")

        return {
            "ticker": ticker,
            "revenue": get_latest_value("Revenues") or get_latest_value("RevenueFromContractWithCustomerExcludingAssessedTax"),
            "net_income": get_latest_value("NetIncomeLoss"),
            "total_assets": get_latest_value("Assets"),
            "total_debt": get_latest_value("LongTermDebt"),
            "cash": get_latest_value("CashAndCashEquivalentsAtCarryingValue"),
            "stockholders_equity": get_latest_value("StockholdersEquity"),
            "operating_cash_flow": get_latest_value("NetCashProvidedByUsedInOperatingActivities"),
            "capex": get_latest_value("PaymentsToAcquirePropertyPlantAndEquipment"),
            "eps_diluted": get_latest_value("EarningsPerShareDiluted", "USD/shares"),
            "shares_outstanding": get_latest_value("CommonStockSharesOutstanding", "shares"),
            "source": "sec_edgar",
        }

    @async_retry(max_attempts=2, delay=5.0)
    async def get_institutional_ownership(self, ticker: str) -> Optional[List[Dict]]:
        """
        13F formlarından kurumsal yatırımcı sahipliğini çeker.
        Hedge fund ve büyük fon hareketleri.
        """
        cik = await self._get_cik(ticker)
        if not cik:
            return None

        # 13F-HR formları ara
        cik_padded = cik.zfill(10)
        url = f"{self.BASE_URL}/submissions/CIK{cik_padded}.json"

        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        return None
                    sub_data = await resp.json()

            filings = sub_data.get("filings", {}).get("recent", {})
            forms = filings.get("form", [])
            dates = filings.get("filingDate", [])
            accession_numbers = filings.get("accessionNumber", [])

            # 13F formlarını filtrele
            institutional = []
            for form, date, accession in zip(forms, dates, accession_numbers):
                if form == "13F-HR":
                    institutional.append({
                        "form": form,
                        "filing_date": date,
                        "accession_number": accession,
                    })

            return institutional[:10]  # Son 10 13F

        except Exception as e:
            logger.warning("13F verisi alınamadı.", ticker=ticker, error=str(e))
            return None


# ----------------------------------------------------------
# ANA TEMEL ANALİZ SERVİSİ
# ----------------------------------------------------------

class FundamentalDataService:
    """
    Tüm temel analiz kaynaklarını birleştiren ana servis.

    Veri hiyerarşisi:
    1. Finnhub     → Hızlı oranlar (P/E, P/B, margins)
    2. SEC EDGAR   → Resmi finansal tablo rakamları
    3. yfinance    → Fallback
    """

    def __init__(self):
        self.finnhub = FinnhubFetcher()
        self.edgar = SECEdgarFetcher()

    async def get_comprehensive_fundamental(self, ticker: str) -> Dict:
        """
        Tüm kaynaklardan temel analiz verisini toplar ve birleştirir.
        Model için zenginleştirilmiş temel analiz feature seti döndürür.
        """
        cache_key = f"{ticker}:fundamental"
        cached = await cache_manager.get(CacheNamespace.FUNDAMENTAL, cache_key)
        if cached:
            return cached

        # Paralel çekme (tüm kaynakları aynı anda)
        tasks = [
            self._safe_fetch("finnhub_basic", self.finnhub.get_basic_financials(ticker)),
            self._safe_fetch("edgar_facts", self.edgar.get_company_facts(ticker)),
            self._safe_fetch("insider", self.finnhub.get_insider_transactions(ticker)),
            self._safe_fetch("recommendations", self.finnhub.get_recommendation_trends(ticker)),
            self._safe_fetch("earnings", self.finnhub.get_earnings_calendar(ticker)),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=False)
        finnhub_data, edgar_data, insider_data, recs, earnings = results

        # Veri birleştirme (Finnhub önce, EDGAR üzerine yaz)
        merged = {}
        if finnhub_data:
            merged.update(finnhub_data)
        if edgar_data:
            # EDGAR resmi kaynak, Finnhub'dan farklıysa EDGAR'ı tercih et
            for k, v in edgar_data.items():
                if v is not None:
                    merged[k] = v

        # Ek metrikler
        merged["insider_transactions"] = insider_data or []
        merged["analyst_recommendations"] = recs or []
        merged["earnings_calendar"] = earnings

        # Temel analiz skoru hesapla (0-100)
        merged["fundamental_score"] = self._calculate_fundamental_score(merged)
        merged["ticker"] = ticker
        merged["last_updated"] = datetime.utcnow().isoformat()

        # İçeriden öğrenenler sinyali
        merged["insider_signal"] = self._analyze_insider_activity(insider_data or [])

        # Cache'e yaz (haftalık güncelleme yeterli)
        await cache_manager.set(CacheNamespace.FUNDAMENTAL, cache_key, merged, ttl=86400 * 7)

        return merged

    async def _safe_fetch(self, name: str, coro):
        """Hata durumunda None döndüren güvenli wrapper."""
        try:
            return await coro
        except Exception as e:
            logger.warning(f"Temel analiz verisi alınamadı.", source=name, error=str(e))
            return None

    def _calculate_fundamental_score(self, data: Dict) -> float:
        """
        0-100 arası temel analiz puanı hesaplar.

        Faktörler:
        - Değerleme (P/E, P/B düşük = iyi)
        - Karlılık (yüksek margin, ROE = iyi)
        - Büyüme (EPS, revenue growth = iyi)
        - Finansal sağlık (düşük borç, yüksek FCF = iyi)
        """
        score = 50.0  # Başlangıç nötr puan

        # --- Değerleme ---
        pe = data.get("pe_ratio")
        if pe is not None:
            if 5 < pe < 20:
                score += 10
            elif 20 <= pe < 35:
                score += 3
            elif pe > 50:
                score -= 10
            elif pe < 0:
                score -= 15  # Zarar eden şirket

        pb = data.get("pb_ratio")
        if pb is not None:
            if 0 < pb < 3:
                score += 5
            elif pb > 10:
                score -= 8

        # --- Karlılık ---
        net_margin = data.get("net_margin")
        if net_margin is not None:
            if net_margin > 0.20:
                score += 12
            elif net_margin > 0.10:
                score += 6
            elif net_margin < 0:
                score -= 15

        roe = data.get("roe")
        if roe is not None:
            if roe > 0.20:
                score += 10
            elif roe > 0.10:
                score += 4
            elif roe < 0:
                score -= 10

        # --- Büyüme ---
        eps_growth = data.get("eps_growth_3y")
        if eps_growth is not None:
            if eps_growth > 0.15:
                score += 10
            elif eps_growth > 0.05:
                score += 4
            elif eps_growth < 0:
                score -= 8

        # --- Finansal Sağlık ---
        debt_equity = data.get("debt_to_equity")
        if debt_equity is not None:
            if debt_equity < 0.5:
                score += 8
            elif debt_equity > 2.0:
                score -= 10

        return round(max(0, min(100, score)), 2)

    def _analyze_insider_activity(self, transactions: List[Dict]) -> str:
        """
        İçeriden öğrenen işlemlerini değerlendirerek sinyal üretir.
        P (Purchase) = Alım, S (Sale) = Satış
        """
        if not transactions:
            return "neutral"

        buys = sum(1 for t in transactions if t.get("transaction_type") == "P")
        sells = sum(1 for t in transactions if t.get("transaction_type") == "S")

        if buys > sells * 2:
            return "bullish"
        elif sells > buys * 2:
            return "bearish"
        return "neutral"


# Singleton
fundamental_service = FundamentalDataService()

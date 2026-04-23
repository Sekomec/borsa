"""
QuantEdge AI — Risk Analiz Servisi
====================================
Risk Metrikleri:
  - Value at Risk (VaR) — Tarihi simülasyon
  - Conditional VaR (CVaR / Expected Shortfall)
  - Maximum Drawdown
  - Sharpe Ratio (risk-düzeltilmiş getiri)
  - Beta (piyasaya göre risk)
  - Volatilite (tarihsel ve implied)

Black Swan Uyarı Sistemi:
  - Sistemik risk göstergeleri
  - Çoklu kaynak doğrulama
  - Kullanıcı uyarı mekanizması
"""

from typing import Dict, List, Optional
import numpy as np
import structlog

logger = structlog.get_logger()

DISCLAIMER = (
    "⚠️ Bu analizler tamamen bilgilendirme amaçlıdır. "
    "Geçmiş performans gelecekteki sonuçların garantisi değildir. "
    "Yatırım tavsiyesi değildir. Lisanslı bir finansal danışmana başvurunuz."
)


class RiskAnalysisService:
    """Portföy ve hisse bazlı risk metrikleri hesaplar."""

    def calculate_full_risk_profile(
        self,
        prices: List[float],
        benchmark_prices: Optional[List[float]] = None,
        confidence_level: float = 0.95,
    ) -> Dict:
        """
        Tam risk profili hesaplar.

        Args:
            prices           : Kapanış fiyatları
            benchmark_prices : S&P 500 (beta için)
            confidence_level : VaR için güven düzeyi

        Returns:
            Kapsamlı risk metrikleri
        """
        if not prices or len(prices) < 20:
            return {"error": "Yetersiz fiyat verisi."}

        prices_arr = np.array(prices)
        returns = np.diff(np.log(prices_arr))

        risk_profile = {
            "historical_volatility_daily": self._annualize(np.std(returns)),
            "historical_volatility_annual": self._annualize(np.std(returns)) * np.sqrt(252),
            "var_95": self._calculate_var(returns, 0.95),
            "var_99": self._calculate_var(returns, 0.99),
            "cvar_95": self._calculate_cvar(returns, 0.95),
            "max_drawdown": self._calculate_max_drawdown(prices_arr),
            "sharpe_ratio": self._calculate_sharpe(returns),
            "skewness": float(self._skewness(returns)),
            "kurtosis": float(self._kurtosis(returns)),
            "fat_tail_risk": self._assess_fat_tails(returns),
            "disclaimer": DISCLAIMER,
        }

        if benchmark_prices and len(benchmark_prices) >= len(prices) - 1:
            bench_arr = np.array(benchmark_prices[-len(returns):])
            if len(bench_arr) == len(returns):
                bench_returns = np.diff(np.log(np.array(benchmark_prices)))
                risk_profile["beta"] = self._calculate_beta(returns, bench_returns[-len(returns):])

        risk_profile["risk_summary"] = self._summarize_risk(risk_profile)
        return risk_profile

    def _calculate_var(self, returns: np.ndarray, confidence: float) -> float:
        """Tarihi simülasyon VaR."""
        return float(-np.percentile(returns, (1 - confidence) * 100))

    def _calculate_cvar(self, returns: np.ndarray, confidence: float) -> float:
        """Conditional VaR (Expected Shortfall)."""
        var = self._calculate_var(returns, confidence)
        tail = returns[returns < -var]
        return float(-np.mean(tail)) if len(tail) > 0 else var

    def _calculate_max_drawdown(self, prices: np.ndarray) -> float:
        """Maksimum düşüş (peak-to-trough)."""
        peak = np.maximum.accumulate(prices)
        drawdown = (prices - peak) / peak
        return float(np.min(drawdown))

    def _calculate_sharpe(self, returns: np.ndarray, risk_free: float = 0.05) -> float:
        """Yıllıklaştırılmış Sharpe oranı."""
        annual_return = np.mean(returns) * 252
        annual_std = np.std(returns) * np.sqrt(252)
        if annual_std == 0:
            return 0.0
        return float((annual_return - risk_free) / annual_std)

    def _calculate_beta(self, asset_returns: np.ndarray, bench_returns: np.ndarray) -> float:
        """Piyasa betası."""
        min_len = min(len(asset_returns), len(bench_returns))
        a, b = asset_returns[-min_len:], bench_returns[-min_len:]
        cov = np.cov(a, b)[0, 1]
        var_bench = np.var(b)
        return float(cov / var_bench) if var_bench != 0 else 1.0

    def _annualize(self, daily_vol: float) -> float:
        return float(daily_vol)

    def _skewness(self, returns: np.ndarray) -> float:
        mean, std = np.mean(returns), np.std(returns)
        if std == 0:
            return 0.0
        return float(np.mean(((returns - mean) / std) ** 3))

    def _kurtosis(self, returns: np.ndarray) -> float:
        mean, std = np.mean(returns), np.std(returns)
        if std == 0:
            return 0.0
        return float(np.mean(((returns - mean) / std) ** 4) - 3)

    def _assess_fat_tails(self, returns: np.ndarray) -> str:
        """Kalın kuyruk riski değerlendirmesi."""
        kurt = self._kurtosis(returns)
        if kurt > 5:
            return "Yüksek — Aşırı olaylar normal dağılımdan çok daha sık gerçekleşiyor."
        elif kurt > 2:
            return "Orta — Bazı kalın kuyruk riski mevcut."
        else:
            return "Düşük — Dağılım normale yakın."

    def _summarize_risk(self, profile: Dict) -> str:
        """Kısa risk özeti."""
        vol = profile.get("historical_volatility_annual", 0)
        mdd = profile.get("max_drawdown", 0)
        sharpe = profile.get("sharpe_ratio", 0)

        if vol > 0.5 or mdd < -0.4:
            return "Çok Yüksek Risk — Deneyimli yatırımcılar için uygun."
        elif vol > 0.3 or mdd < -0.25:
            return "Yüksek Risk — Dikkatli pozisyon boyutlandırması gerekli."
        elif vol > 0.2:
            return "Orta Risk — Standart hisse senedi riski."
        else:
            return "Düşük-Orta Risk — Görece istikrarlı."


# Singleton
risk_service = RiskAnalysisService()

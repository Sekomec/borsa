import { useEffect, useMemo, useState } from 'react';

import type {
  FundamentalResponse,
  MacroSnapshot,
  OHLCVBar,
  PredictionRequest,
  PredictionResponse,
  SentimentResponse,
  StockInfo,
  TechnicalAnalysisResponse,
  Timeframe,
} from '@/types';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    cache: 'no-store',
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => '');
    throw new Error(txt || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  getOHLCV: (ticker: string, timeframe: string, limit: number) =>
    fetchJSON<{ ticker: string; timeframe: string; bars: number; data: OHLCVBar[] }>(
      `/api/v1/market/${encodeURIComponent(ticker)}/ohlcv?timeframe=${encodeURIComponent(timeframe)}&limit=${limit}`
    ),
  getSentiment: (ticker: string) =>
    fetchJSON<SentimentResponse>(`/api/v1/sentiment/${encodeURIComponent(ticker)}`),
  getMacroSnapshot: () => fetchJSON<MacroSnapshot>(`/api/v1/macro/snapshot`),
  getPrediction: (req: PredictionRequest) =>
    fetchJSON<PredictionResponse>(`/api/v1/stocks/predict`, {
      method: 'POST',
      body: JSON.stringify(req),
    }),
  // Optional endpoints (if you later add them server-side)
  getFundamental: async (ticker: string): Promise<FundamentalResponse | null> => {
    try {
      return await fetchJSON<any>(`/api/v1/stocks/${encodeURIComponent(ticker)}/fundamental`);
    } catch {
      return null;
    }
  },
  getTechnical: async (ticker: string, timeframe: string): Promise<TechnicalAnalysisResponse | null> => {
    try {
      return await fetchJSON<any>(`/api/v1/stocks/${encodeURIComponent(ticker)}/technical?timeframe=${encodeURIComponent(timeframe)}`);
    } catch {
      return null;
    }
  },
  getStockInfo: async (ticker: string): Promise<StockInfo | null> => {
    try {
      // backend service already supports stock_info internally; this endpoint can be added later
      return await fetchJSON<any>(`/api/v1/stocks/${encodeURIComponent(ticker)}/info`);
    } catch {
      return null;
    }
  },
  getQuote: async (ticker: string): Promise<{ price: number } | null> => {
    try {
      return await fetchJSON<any>(`/api/v1/stocks/${encodeURIComponent(ticker)}/quote`);
    } catch {
      return null;
    }
  },
};

function useAsync<T>(fn: () => Promise<T>, deps: any[]) {
  const [data, setData] = useState<T | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    fn()
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e?.message || 'error');
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, isLoading, error };
}

export function useOHLCV(ticker: string, timeframe: string, limit: number) {
  return useAsync(() => api.getOHLCV(ticker, timeframe, limit), [ticker, timeframe, limit]);
}

export function useSentiment(ticker: string) {
  return useAsync(() => api.getSentiment(ticker), [ticker]);
}

export function useMacroSnapshot() {
  return useAsync(() => api.getMacroSnapshot(), []);
}

export function useFundamental(ticker: string) {
  return useAsync(() => api.getFundamental(ticker), [ticker]);
}

export function useTechnicalAnalysis(ticker: string, timeframe: Timeframe) {
  return useAsync(() => api.getTechnical(ticker, timeframe), [ticker, timeframe]);
}

export function useStockInfo(ticker: string) {
  return useAsync(() => api.getStockInfo(ticker), [ticker]);
}

export function useQuote(ticker: string) {
  return useAsync(() => api.getQuote(ticker), [ticker]);
}

export function formatPrice(v?: number | null) {
  if (v === undefined || v === null || Number.isNaN(v)) return '—';
  return `$${v.toFixed(2)}`;
}

export function formatPct(v?: number | null) {
  if (v === undefined || v === null || Number.isNaN(v)) return '—';
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
}

export function formatMarketCap(v?: number | null) {
  if (!v) return '—';
  const abs = Math.abs(v);
  if (abs >= 1e12) return `${(v / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
  return `${v.toFixed(0)}`;
}

export function toTVCandles(bars: OHLCVBar[]) {
  return bars
    .map((b) => {
      const t = new Date(b.timestamp).getTime();
      return {
        time: Number.isFinite(t) ? Math.floor(t / 1000) : null,
        open: b.open_price,
        high: b.high_price,
        low: b.low_price,
        close: b.close_price,
      };
    })
    .filter((c): c is { time: number; open: number; high: number; low: number; close: number } => c.time !== null)
    .sort((a, b) => a.time - b.time);
}

export function toTVVolume(bars: OHLCVBar[]) {
  return bars
    .map((b) => {
      const t = new Date(b.timestamp).getTime();
      return {
        time: Number.isFinite(t) ? Math.floor(t / 1000) : null,
        value: b.volume ?? 0,
        color: b.close_price >= b.open_price ? 'rgba(16,185,129,0.35)' : 'rgba(239,68,68,0.35)',
      };
    })
    .filter((v): v is { time: number; value: number; color: string } => v.time !== null)
    .sort((a, b) => a.time - b.time);
}


// ============================================================
// QuantEdge AI — Market Data Custom Hook'ları
// ============================================================
// useMarketData: OHLCV + quote + teknik analiz birleşik hook
// usePrediction : Tek noktadan tahmin yönetimi

import { useState, useCallback, useEffect } from 'react';
import { api } from '@/lib/api';
import { useOHLCV, useQuote, useStockInfo, useTechnicalAnalysis } from '@/lib/api';
import { usePredictionStore } from '@/store';
import type {
  OHLCVBar, TechnicalAnalysisResult, PredictionResponse,
  Timeframe, StockInfo,
} from '@/types';

// ----------------------------------------------------------
// useMarketData — Hisse için tüm piyasa verisi
// ----------------------------------------------------------

interface MarketDataResult {
  ticker:      string;
  bars:        OHLCVBar[];
  currentPrice: number | null;
  priceChange:  number;
  priceChangePct: number;
  stockInfo:   StockInfo | null;
  technical:   TechnicalAnalysisResult | null;
  isLoading:   boolean;
  isError:     boolean;
  refetch:     () => void;
}

export function useMarketData(
  ticker: string | null,
  timeframe: Timeframe = '1d',
  barsLimit = 365,
): MarketDataResult {
  const { data: ohlcvData, isLoading: ohlcvLoading, mutate: mutateOHLCV } =
    useOHLCV(ticker, timeframe, barsLimit);

  const { data: quoteData, mutate: mutateQuote } = useQuote(ticker);
  const { data: stockInfo } = useStockInfo(ticker);
  const { data: technical, mutate: mutateTech } =
    useTechnicalAnalysis(ticker, timeframe);

  const bars  = ohlcvData?.data ?? [];
  const price = quoteData?.price ?? bars.at(-1)?.close_price ?? null;

  // Fiyat değişimi hesapla
  let priceChange    = 0;
  let priceChangePct = 0;
  if (bars.length >= 2) {
    const prev = bars.at(-2)!.close_price;
    const curr = bars.at(-1)!.close_price;
    priceChange    = curr - prev;
    priceChangePct = (priceChange / prev) * 100;
  }

  const refetch = useCallback(() => {
    mutateOHLCV();
    mutateQuote();
    mutateTech();
  }, [mutateOHLCV, mutateQuote, mutateTech]);

  return {
    ticker:         ticker ?? '',
    bars,
    currentPrice:   price,
    priceChange:    priceChange,
    priceChangePct: priceChangePct,
    stockInfo:      stockInfo ?? null,
    technical:      technical ?? null,
    isLoading:      ohlcvLoading,
    isError:        !ohlcvLoading && bars.length === 0,
    refetch,
  };
}

// ----------------------------------------------------------
// usePrediction — Tahmin yönetimi
// ----------------------------------------------------------

interface PredictionResult {
  prediction:   PredictionResponse | null;
  isLoading:    boolean;
  error:        string | null;
  fetch:        (tf?: Timeframe) => Promise<void>;
  clearError:   () => void;
}

export function usePrediction(ticker: string, timeframe: Timeframe = '1d'): PredictionResult {
  const { predictions, setPrediction, isLoadingPrediction, setIsLoadingPrediction } =
    usePredictionStore();

  const key        = `${ticker}:${timeframe}`;
  const prediction = predictions[key] ?? null;

  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async (tf: Timeframe = timeframe) => {
    setIsLoadingPrediction(true);
    setError(null);
    try {
      const result = await api.getPrediction({
        ticker,
        timeframe: tf,
        include_technical:   true,
        include_sentiment:   true,
        include_fundamental: true,
        include_macro:       true,
      });
      setPrediction(`${ticker}:${tf}`, result);
    } catch (e: any) {
      setError(e.message ?? 'Tahmin alınamadı.');
    } finally {
      setIsLoadingPrediction(false);
    }
  }, [ticker, timeframe, setPrediction, setIsLoadingPrediction]);

  return {
    prediction,
    isLoading: isLoadingPrediction,
    error,
    fetch,
    clearError: () => setError(null),
  };
}

// ----------------------------------------------------------
// useWatchlistPrices — Watchlist fiyatlarını toplu çek
// ----------------------------------------------------------

interface WatchlistPrice {
  ticker: string;
  price:  number | null;
  change: number;
  changePct: number;
}

export function useWatchlistPrices(tickers: string[]): {
  prices: WatchlistPrice[];
  isLoading: boolean;
} {
  const [prices, setPrices] = useState<WatchlistPrice[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const fetchAll = useCallback(async () => {
    if (!tickers.length) return;
    setIsLoading(true);
    try {
      const results = await Promise.allSettled(
        tickers.map(t => api.getQuote(t))
      );
      const priceData = tickers.map((ticker, i) => {
        const result = results[i];
        return {
          ticker,
          price:     result.status === 'fulfilled' ? result.value?.price ?? null : null,
          change:    0,
          changePct: 0,
        };
      });
      setPrices(priceData);
    } catch {
      // Sessizce başarısız
    } finally {
      setIsLoading(false);
    }
  }, [tickers.join(',')]);

  useEffect(() => {
    fetchAll();
    // 60 saniyede bir güncelle
    const interval = setInterval(fetchAll, 60_000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  return { prices, isLoading };
}

// ----------------------------------------------------------
// useMarketStatus — Piyasa açık/kapalı kontrolü
// ----------------------------------------------------------

export function useMarketStatus(): {
  isOpen:    boolean;
  nextEvent: string;
  timezone:  string;
} {
  const now = new Date();
  const etTime = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
  const hours   = etTime.getHours();
  const minutes = etTime.getMinutes();
  const day     = etTime.getDay(); // 0=Pazar, 6=Cumartesi
  const timeNum = hours * 100 + minutes;

  const isWeekday = day >= 1 && day <= 5;
  const isDuringHours = timeNum >= 930 && timeNum < 1600;
  const isOpen = isWeekday && isDuringHours;

  let nextEvent = '';
  if (!isOpen) {
    if (!isWeekday || timeNum >= 1600) {
      nextEvent = 'Yarın 09:30 ET açılış';
    } else {
      nextEvent = 'Bugün 09:30 ET açılış';
    }
  } else {
    const closeHour = 16, closeMin = 0;
    const diffMin = (closeHour * 60 + closeMin) - (hours * 60 + minutes);
    nextEvent = `${diffMin} dk içinde kapanış`;
  }

  return { isOpen, nextEvent, timezone: 'ET' };
}

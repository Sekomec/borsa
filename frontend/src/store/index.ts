import { create } from 'zustand';

import type { PredictionResponse, Timeframe } from '@/types';

type UIState = {
  sidebarOpen: boolean;
  disclaimerDismissed: boolean;
  toggleSidebar: () => void;
  dismissDisclaimer: () => void;
};

export const useUIStore = create<UIState>((set) => ({
  sidebarOpen: true,
  disclaimerDismissed: false,
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  dismissDisclaimer: () => set({ disclaimerDismissed: true }),
}));

type StockState = {
  selectedTicker: string;
  watchlist: string[];
  recentSearches: string[];
  setSelectedTicker: (t: string) => void;
  addToWatchlist: (t: string) => void;
  removeFromWatchlist: (t: string) => void;
  addRecentSearch: (t: string) => void;
};

export const useStockStore = create<StockState>((set) => ({
  selectedTicker: 'AAPL',
  watchlist: ['AAPL', 'MSFT', 'NVDA'],
  recentSearches: [],
  setSelectedTicker: (t) => set({ selectedTicker: t.toUpperCase() }),
  addToWatchlist: (t) =>
    set((s) => ({ watchlist: Array.from(new Set([...s.watchlist, t.toUpperCase()])) })),
  removeFromWatchlist: (t) =>
    set((s) => ({ watchlist: s.watchlist.filter((x) => x !== t.toUpperCase()) })),
  addRecentSearch: (t) =>
    set((s) => ({ recentSearches: [t.toUpperCase(), ...s.recentSearches].slice(0, 12) })),
}));

type ChartSettings = {
  showSMA20: boolean;
  showSMA50: boolean;
  showSMA200: boolean;
  showVWAP: boolean;
  showBollingerBands: boolean;
};

type ChartState = {
  timeframe: Timeframe;
  chartSettings: ChartSettings;
  setTimeframe: (tf: Timeframe) => void;
  toggleSetting: (k: keyof ChartSettings) => void;
};

export const useChartStore = create<ChartState>((set) => ({
  timeframe: '1d',
  chartSettings: {
    showSMA20: true,
    showSMA50: true,
    showSMA200: false,
    showVWAP: true,
    showBollingerBands: false,
  },
  setTimeframe: (tf) => set({ timeframe: tf }),
  toggleSetting: (k) =>
    set((s) => ({ chartSettings: { ...s.chartSettings, [k]: !s.chartSettings[k] } })),
}));

type PredictionState = {
  predictions: Record<string, PredictionResponse>;
  setPrediction: (key: string, value: PredictionResponse) => void;
};

export const usePredictionStore = create<PredictionState>((set) => ({
  predictions: {},
  setPrediction: (key, value) => set((s) => ({ predictions: { ...s.predictions, [key]: value } })),
}));


'use client';

// ============================================================
// QuantEdge AI — Layout Bileşenleri
// Sidebar | TopBar | StockHeader | MacroTicker
// ============================================================

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search, Star, StarOff, TrendingUp, TrendingDown,
  BarChart2, Settings, Bell, ChevronLeft, ChevronRight,
  Activity, Globe, Cpu, AlertCircle, Eye, Zap,
} from 'lucide-react';
import { useStockStore, useUIStore } from '@/store';
import { useMacroSnapshot, formatPrice, formatPct, formatMarketCap } from '@/lib/api';
import type { StockInfo, MacroSnapshot } from '@/types';

// ----------------------------------------------------------
// SIDEBAR
// ----------------------------------------------------------

const POPULAR_TICKERS = [
  { ticker: 'AAPL', name: 'Apple', change: 1.24 },
  { ticker: 'MSFT', name: 'Microsoft', change: 0.87 },
  { ticker: 'NVDA', name: 'NVIDIA', change: 3.41 },
  { ticker: 'GOOGL', name: 'Alphabet', change: -0.32 },
  { ticker: 'TSLA', name: 'Tesla', change: 2.15 },
  { ticker: 'AMZN', name: 'Amazon', change: -0.89 },
  { ticker: 'META', name: 'Meta', change: 1.67 },
  { ticker: 'JPM', name: 'JP Morgan', change: 0.45 },
];

export function Sidebar() {
  const { sidebarOpen, toggleSidebar } = useUIStore();
  const {
    selectedTicker, setSelectedTicker,
    watchlist, addToWatchlist, removeFromWatchlist,
    recentSearches, addRecentSearch,
  } = useStockStore();

  const [search, setSearch] = useState('');
  const [searchFocused, setSearchFocused] = useState(false);

  const handleSelect = (ticker: string) => {
    setSelectedTicker(ticker);
    addRecentSearch(ticker);
    setSearch('');
  };

  const filteredPopular = POPULAR_TICKERS.filter((t) =>
    t.ticker.includes(search.toUpperCase()) || t.name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <motion.aside
      animate={{ width: sidebarOpen ? 240 : 56 }}
      transition={{ duration: 0.2, ease: 'easeInOut' }}
      className="flex flex-col bg-surface-1 border-r border-border-subtle flex-shrink-0 overflow-hidden"
    >
      {/* Logo & Toggle */}
      <div className="flex items-center justify-between px-3 py-4 border-b border-border-subtle">
        <AnimatePresence>
          {sidebarOpen && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex items-center gap-2"
            >
              <div className="w-7 h-7 rounded-lg bg-accent-gradient border border-accent-cyan/30
                flex items-center justify-center flex-shrink-0">
                <Zap size={14} className="text-accent-cyan" />
              </div>
              <span className="font-display font-bold text-text-bright text-sm whitespace-nowrap">
                QuantEdge
              </span>
            </motion.div>
          )}
        </AnimatePresence>
        <button
          onClick={toggleSidebar}
          className="p-1 rounded-lg text-text-muted hover:text-text-primary hover:bg-surface-3 transition-all"
        >
          {sidebarOpen ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
        </button>
      </div>

      {/* Arama */}
      {sidebarOpen && (
        <div className="px-3 py-3">
          <div className="relative">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted" />
            <input
              type="text"
              placeholder="Ticker ara..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onFocus={() => setSearchFocused(true)}
              onBlur={() => setTimeout(() => setSearchFocused(false), 200)}
              className="input pl-8 py-1.5 text-xs"
            />
          </div>
        </div>
      )}

      {/* Ticker Listesi */}
      <div className="flex-1 overflow-y-auto px-2 space-y-0.5">
        {sidebarOpen && (
          <>
            {/* İzleme Listesi */}
            {watchlist.length > 0 && (
              <div className="mb-2">
                <p className="text-[10px] text-text-muted uppercase tracking-widest px-2 py-2">
                  İzleme Listesi
                </p>
                {watchlist.map((ticker) => (
                  <SidebarTickerRow
                    key={ticker}
                    ticker={ticker}
                    isActive={selectedTicker === ticker}
                    isWatched={true}
                    onSelect={handleSelect}
                    onToggleWatch={() => removeFromWatchlist(ticker)}
                  />
                ))}
              </div>
            )}

            {/* Popüler */}
            <p className="text-[10px] text-text-muted uppercase tracking-widest px-2 py-2">
              {search ? 'Sonuçlar' : 'Popüler'}
            </p>
            {filteredPopular.map((item) => (
              <SidebarTickerRow
                key={item.ticker}
                ticker={item.ticker}
                name={item.name}
                change={item.change}
                isActive={selectedTicker === item.ticker}
                isWatched={watchlist.includes(item.ticker)}
                onSelect={handleSelect}
                onToggleWatch={() =>
                  watchlist.includes(item.ticker)
                    ? removeFromWatchlist(item.ticker)
                    : addToWatchlist(item.ticker)
                }
              />
            ))}
          </>
        )}

        {!sidebarOpen && (
          <div className="space-y-1 pt-2">
            {watchlist.slice(0, 6).map((ticker) => (
              <button
                key={ticker}
                onClick={() => handleSelect(ticker)}
                title={ticker}
                className={`w-full flex items-center justify-center py-2 rounded-lg text-xs font-mono font-bold transition-all
                  ${selectedTicker === ticker
                    ? 'bg-accent-cyan/10 text-accent-cyan'
                    : 'text-text-muted hover:text-text-primary hover:bg-surface-3'}`}
              >
                {ticker.slice(0, 2)}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Alt bölüm */}
      <div className="border-t border-border-subtle p-2">
        <button className="w-full flex items-center gap-2 px-2 py-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-surface-3 transition-all text-xs">
          <Settings size={14} />
          {sidebarOpen && <span>Ayarlar</span>}
        </button>
      </div>
    </motion.aside>
  );
}

function SidebarTickerRow({
  ticker, name, change, isActive, isWatched, onSelect, onToggleWatch,
}: {
  ticker: string; name?: string; change?: number;
  isActive: boolean; isWatched: boolean;
  onSelect: (t: string) => void; onToggleWatch: () => void;
}) {
  return (
    <div
      className={`group flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer transition-all
        ${isActive ? 'bg-surface-4 text-text-bright' : 'hover:bg-surface-3 text-text-secondary hover:text-text-primary'}`}
      onClick={() => onSelect(ticker)}
    >
      <div className="flex-1 min-w-0">
        <p className="text-xs font-mono font-semibold truncate">{ticker}</p>
        {name && <p className="text-[10px] text-text-muted truncate">{name}</p>}
      </div>
      {change !== undefined && (
        <span className={`text-[10px] font-mono ${change >= 0 ? 'text-bull' : 'text-bear'}`}>
          {change >= 0 ? '+' : ''}{change.toFixed(2)}%
        </span>
      )}
      <button
        onClick={(e) => { e.stopPropagation(); onToggleWatch(); }}
        className="opacity-0 group-hover:opacity-100 transition-opacity"
      >
        {isWatched
          ? <Star size={11} className="text-amber-400 fill-amber-400" />
          : <StarOff size={11} className="text-text-muted" />}
      </button>
    </div>
  );
}

// ----------------------------------------------------------
// TOP BAR
// ----------------------------------------------------------

export function TopBar() {
  return (
    <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle bg-surface-1">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-bull animate-pulse" />
          <span className="text-[11px] text-text-muted">Piyasa Açık</span>
        </div>
        <span className="text-border-strong">|</span>
        <span className="text-[11px] text-text-muted font-mono">
          {new Date().toLocaleString('tr-TR', { hour: '2-digit', minute: '2-digit', timeZone: 'America/New_York' })} ET
        </span>
      </div>

      <div className="flex items-center gap-2">
        <button className="btn-ghost px-2 py-1.5 text-xs gap-1">
          <Eye size={13} /> Screener
        </button>
        <button className="btn-ghost px-2 py-1.5 text-xs gap-1">
          <Bell size={13} /> Uyarılar
        </button>
        <div className="w-7 h-7 rounded-full bg-accent-gradient border border-accent-cyan/30
          flex items-center justify-center cursor-pointer">
          <span className="text-[10px] font-bold text-accent-cyan">QE</span>
        </div>
      </div>
    </div>
  );
}

// ----------------------------------------------------------
// STOCK HEADER
// ----------------------------------------------------------

export function StockHeader({
  ticker, stockInfo, quote,
}: {
  ticker: string;
  stockInfo?: StockInfo | null;
  quote?: { price: number } | null;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-center justify-between"
    >
      <div className="flex items-center gap-3">
        {/* Ticker logo placeholder */}
        <div className="w-10 h-10 rounded-xl bg-surface-3 border border-border-subtle
          flex items-center justify-center font-mono font-bold text-sm text-accent-cyan">
          {ticker.slice(0, 2)}
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="font-display font-bold text-lg text-text-bright">{ticker}</h1>
            {stockInfo?.exchange && (
              <span className="badge badge-neutral text-[10px]">{stockInfo.exchange}</span>
            )}
          </div>
          <p className="text-sm text-text-secondary">
            {stockInfo?.company_name || ticker}
            {stockInfo?.sector && (
              <span className="text-text-muted"> · {stockInfo.sector}</span>
            )}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-6">
        {quote?.price && (
          <div className="text-right">
            <p className="font-mono text-2xl font-bold text-text-bright">
              {formatPrice(quote.price)}
            </p>
          </div>
        )}
        {stockInfo?.market_cap && (
          <div className="text-right hidden md:block">
            <p className="text-[10px] text-text-muted uppercase tracking-wide">Piyasa Değeri</p>
            <p className="font-mono text-sm font-semibold text-text-primary">
              {formatMarketCap(stockInfo.market_cap)}
            </p>
          </div>
        )}
      </div>
    </motion.div>
  );
}

// ----------------------------------------------------------
// MACRO TICKER
// ----------------------------------------------------------

const MACRO_FALLBACK = [
  { label: 'S&P 500', value: '5,234.18', change: '+0.42%', up: true },
  { label: 'NASDAQ', value: '16,384.47', change: '+0.61%', up: true },
  { label: 'VIX', value: '18.24', change: '-2.14%', up: false },
  { label: 'DXY', value: '104.82', change: '+0.18%', up: true },
  { label: '10Y', value: '4.42%', change: '+0.03', up: true },
  { label: 'FED', value: '5.33%', change: '0.00', up: true },
  { label: 'Gold', value: '$2,318', change: '+0.87%', up: true },
  { label: 'BTC', value: '$62,441', change: '+1.34%', up: true },
];

export function MacroTicker() {
  const { data: macro } = useMacroSnapshot();

  const items = macro ? [
    { label: 'FED', value: `${macro.fed_rate?.toFixed(2)}%`, change: '', up: true },
    { label: '10Y', value: `${macro.us_10y_yield?.toFixed(2)}%`, change: '', up: (macro.yield_curve_spread || 0) > 0 },
    { label: 'VIX', value: macro.vix?.toFixed(2) || '—', change: '', up: (macro.vix || 20) < 20 },
    { label: 'DXY', value: macro.dxy?.toFixed(2) || '—', change: '', up: true },
    { label: 'CPI', value: `${macro.cpi_yoy_pct?.toFixed(1)}%`, change: '', up: (macro.cpi_yoy_pct || 3) < 3 },
  ] : MACRO_FALLBACK;

  const doubleItems = [...items, ...items];  // Sonsuz scroll için kopyala

  return (
    <div className="bg-surface-2 border-b border-border-subtle py-1.5 overflow-hidden">
      <div className="ticker-wrapper">
        <div className="ticker-inner flex gap-8">
          {doubleItems.map((item, i) => (
            <div key={i} className="flex items-center gap-2 flex-shrink-0">
              <span className="text-[10px] text-text-muted uppercase tracking-wider">{item.label}</span>
              <span className="text-[11px] font-mono font-semibold text-text-primary">{item.value}</span>
              {item.change && (
                <span className={`text-[10px] font-mono ${item.up ? 'text-bull' : 'text-bear'}`}>
                  {item.change}
                </span>
              )}
              <span className="text-border-subtle">·</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ----------------------------------------------------------
// DISCLAIMER BANNER
// ----------------------------------------------------------

export function DisclaimerBanner() {
  const { dismissDisclaimer } = useUIStore();

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: 'auto' }}
      exit={{ opacity: 0, height: 0 }}
      className="flex items-start gap-3 p-3 bg-amber-500/5 border border-amber-500/20
        rounded-xl text-amber-400/90"
    >
      <AlertCircle size={14} className="mt-0.5 flex-shrink-0" />
      <p className="text-[11px] leading-relaxed flex-1">
        <strong>Yasal Uyarı:</strong> Bu platform yalnızca eğitim ve araştırma amaçlıdır.
        Sunulan tahminler ve analizler yatırım tavsiyesi değildir. Geçmiş performans,
        gelecekteki sonuçların garantisi değildir. Her yatırımda sermaye kaybı riski vardır.
        Finansal kararlarınızı lisanslı bir finansal danışmanla alınız.
      </p>
      <button
        onClick={dismissDisclaimer}
        className="text-amber-400/60 hover:text-amber-400 transition-colors text-xs flex-shrink-0"
      >
        Anladım ✕
      </button>
    </motion.div>
  );
}

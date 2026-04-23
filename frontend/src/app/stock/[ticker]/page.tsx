'use client';

// ============================================================
// QuantEdge AI — Hisse Detay Sayfası /stock/[ticker]
// ============================================================

import { useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import { ArrowLeft, Star, StarOff, ExternalLink } from 'lucide-react';
import { useStockStore, useChartStore } from '@/store';
import { Sidebar } from '@/components/layout/Sidebar';
import { TopBar } from '@/components/layout/TopBar';
import { TradingViewChart } from '@/components/charts/TradingViewChart';
import { PredictionPanel } from '@/components/dashboard/PredictionPanel';
import { TechnicalPanel, SentimentPanel, FundamentalPanel } from '@/components/dashboard/AnalysisPanels';
import {
  useOHLCV, useQuote, useStockInfo,
  formatPrice, formatMarketCap,
} from '@/lib/api';

export default function StockDetailPage() {
  const params  = useParams();
  const router  = useRouter();
  const ticker  = (params?.ticker as string || 'AAPL').toUpperCase();

  const { setSelectedTicker, watchlist, addToWatchlist, removeFromWatchlist } = useStockStore();
  const { timeframe } = useChartStore();

  const { data: ohlcvData, isLoading: chartLoading } = useOHLCV(ticker, '1d', 365);
  const { data: quote }     = useQuote(ticker);
  const { data: stockInfo } = useStockInfo(ticker);

  const isWatched = watchlist.includes(ticker);

  // Store'u güncelle
  useEffect(() => {
    setSelectedTicker(ticker);
  }, [ticker, setSelectedTicker]);

  const priceChange = ohlcvData?.data?.length >= 2
    ? ((ohlcvData.data.at(-1)!.close_price - ohlcvData.data.at(-2)!.close_price)
       / ohlcvData.data.at(-2)!.close_price) * 100
    : 0;
  const isUp = priceChange >= 0;

  return (
    <div className="flex h-screen bg-surface-0 overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <TopBar />
        <div className="flex-1 overflow-y-auto">

          {/* Üst başlık şeridi */}
          <div className="sticky top-0 z-20 bg-surface-1/95 backdrop-blur-sm
            border-b border-border-subtle px-4 py-3">
            <div className="flex items-center justify-between">
              {/* Sol: Geri + Hisse bilgisi */}
              <div className="flex items-center gap-4">
                <button
                  onClick={() => router.back()}
                  className="p-1.5 rounded-lg text-text-muted hover:text-text-primary
                    hover:bg-surface-3 transition-all"
                >
                  <ArrowLeft size={16} />
                </button>

                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-surface-3 border border-border-subtle
                    flex items-center justify-center font-mono font-bold text-sm text-accent-cyan">
                    {ticker.slice(0, 2)}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h1 className="font-display font-bold text-lg text-text-bright">
                        {ticker}
                      </h1>
                      {stockInfo?.exchange && (
                        <span className="badge badge-neutral text-[10px]">
                          {stockInfo.exchange}
                        </span>
                      )}
                      {stockInfo?.sector && (
                        <span className="hidden md:inline badge badge-neutral text-[10px]">
                          {stockInfo.sector}
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-text-secondary">
                      {stockInfo?.company_name || ticker}
                    </p>
                  </div>
                </div>
              </div>

              {/* Sağ: Fiyat + Aksiyonlar */}
              <div className="flex items-center gap-4">
                {/* Fiyat */}
                {(quote?.price || ohlcvData?.data?.at(-1)?.close_price) && (
                  <div className="text-right">
                    <p className="font-mono text-xl font-bold text-text-bright">
                      {formatPrice(quote?.price ?? ohlcvData?.data?.at(-1)?.close_price)}
                    </p>
                    <p className={`font-mono text-sm ${isUp ? 'text-bull' : 'text-bear'}`}>
                      {isUp ? '+' : ''}{priceChange.toFixed(2)}%
                    </p>
                  </div>
                )}

                {/* Market Cap */}
                {stockInfo?.market_cap && (
                  <div className="hidden lg:block text-right">
                    <p className="text-[10px] text-text-muted uppercase tracking-wide">
                      Piyasa Değeri
                    </p>
                    <p className="font-mono text-sm font-semibold text-text-primary">
                      {formatMarketCap(stockInfo.market_cap)}
                    </p>
                  </div>
                )}

                {/* İzleme listesi toggle */}
                <button
                  onClick={() =>
                    isWatched
                      ? removeFromWatchlist(ticker)
                      : addToWatchlist(ticker)
                  }
                  className={`p-2 rounded-lg border transition-all ${
                    isWatched
                      ? 'bg-amber-400/10 border-amber-400/30 text-amber-400'
                      : 'bg-surface-3 border-border-subtle text-text-muted hover:text-amber-400'
                  }`}
                  title={isWatched ? 'İzleme listesinden çıkar' : 'İzleme listesine ekle'}
                >
                  {isWatched ? <Star size={16} className="fill-amber-400" /> : <StarOff size={16} />}
                </button>

                {/* Yahoo Finance linki */}
                <a
                  href={`https://finance.yahoo.com/quote/${ticker}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-2 rounded-lg bg-surface-3 border border-border-subtle
                    text-text-muted hover:text-text-primary transition-all"
                  title="Yahoo Finance'de görüntüle"
                >
                  <ExternalLink size={16} />
                </a>
              </div>
            </div>
          </div>

          {/* Ana içerik */}
          <div className="p-4 space-y-4">

            {/* Grafik */}
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              className="card"
            >
              <TradingViewChart
                bars={ohlcvData?.data || []}
                ticker={ticker}
                isLoading={chartLoading}
                height={440}
              />
            </motion.div>

            {/* 2 kolon: Tahmin sol, Teknik sağ */}
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 }}
              >
                <h2 className="text-sm font-semibold text-text-muted uppercase
                  tracking-wide mb-3 flex items-center gap-2">
                  <span>🎯</span> AI Tahmini
                </h2>
                <PredictionPanel ticker={ticker} />
              </motion.div>

              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.15 }}
              >
                <h2 className="text-sm font-semibold text-text-muted uppercase
                  tracking-wide mb-3 flex items-center gap-2">
                  <span>📊</span> Teknik Analiz
                </h2>
                <TechnicalPanel ticker={ticker} />
              </motion.div>
            </div>

            {/* Sentiment + Temel Analiz */}
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 }}
              >
                <h2 className="text-sm font-semibold text-text-muted uppercase
                  tracking-wide mb-3 flex items-center gap-2">
                  <span>💬</span> Piyasa Duyarlılığı
                </h2>
                <SentimentPanel ticker={ticker} />
              </motion.div>

              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.25 }}
              >
                <h2 className="text-sm font-semibold text-text-muted uppercase
                  tracking-wide mb-3 flex items-center gap-2">
                  <span>📋</span> Temel Analiz
                </h2>
                <FundamentalPanel ticker={ticker} />
              </motion.div>
            </div>

          </div>
        </div>
      </div>
    </div>
  );
}

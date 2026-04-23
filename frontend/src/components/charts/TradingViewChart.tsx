'use client';

// ============================================================
// QuantEdge AI — TradingView Lightweight Charts Bileşeni
// ============================================================
// Özellikler:
//   - Candlestick / Line / Area grafik tipleri
//   - Hacim barları (renk kodlu)
//   - SMA 20/50/200 overlay'ları
//   - Bollinger Bands
//   - VWAP çizgisi
//   - Destek / Direnç seviyeleri
//   - Crosshair tooltip
//   - Tam ekran modu

import { useEffect, useRef, useState, useCallback } from 'react';
import {
  createChart,
  ColorType,
  CrosshairMode,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from 'lightweight-charts';
import { motion } from 'framer-motion';
import { useChartStore } from '@/store';
import { toTVCandles, toTVVolume, useTechnicalAnalysis } from '@/lib/api';
import type { OHLCVBar, Timeframe } from '@/types';
import { ChartToolbar } from './ChartToolbar';

interface TradingViewChartProps {
  bars: OHLCVBar[];
  ticker: string;
  isLoading?: boolean;
  height?: number;
}

// TradingView tema ayarları — QuantEdge koyu tema
const CHART_THEME = {
  layout: {
    background: { type: ColorType.Solid, color: '#0D1117' },
    textColor: '#4B5980',
    fontSize: 11,
    fontFamily: 'JetBrains Mono, monospace',
  },
  grid: {
    vertLines: { color: '#1E253510', style: LineStyle.Dotted },
    horzLines: { color: '#1E253520', style: LineStyle.Dotted },
  },
  crosshair: {
    mode: CrosshairMode.Normal,
    vertLine: { color: '#3B82F660', width: 1, style: LineStyle.Dashed, labelBackgroundColor: '#1C2230' },
    horzLine: { color: '#3B82F660', width: 1, style: LineStyle.Dashed, labelBackgroundColor: '#1C2230' },
  },
  rightPriceScale: {
    borderColor: '#1E2535',
    textColor: '#4B5980',
  },
  timeScale: {
    borderColor: '#1E2535',
    textColor: '#4B5980',
    timeVisible: true,
    secondsVisible: false,
  },
};

export function TradingViewChart({
  bars,
  ticker,
  isLoading = false,
  height = 420,
}: TradingViewChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const overlaySeriesRef = useRef<Map<string, ISeriesApi<'Line'>>>(new Map());

  const { chartSettings, timeframe } = useChartStore();
  const { data: taData } = useTechnicalAnalysis(ticker, timeframe as Timeframe);

  const [hoveredPrice, setHoveredPrice] = useState<number | null>(null);
  const [hoveredTime, setHoveredTime] = useState<string | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // ----------------------------------------------------------
  // Grafik oluştur
  // ----------------------------------------------------------
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      ...CHART_THEME,
      width: chartContainerRef.current.clientWidth,
      height,
      handleScroll: { mouseWheel: true, pressedMouseMove: true },
      handleScale: { mouseWheel: true, pinch: true },
    });

    chartRef.current = chart;

    // Candlestick serisi
    const candleSeries = chart.addCandlestickSeries({
      upColor: '#10B981',
      downColor: '#EF4444',
      borderUpColor: '#10B981',
      borderDownColor: '#EF4444',
      wickUpColor: '#10B98180',
      wickDownColor: '#EF444480',
    });
    candleSeriesRef.current = candleSeries;

    // Hacim serisi (candlestick'in altında, %15 yükseklik)
    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    });
    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.85, bottom: 0 },
    });
    volumeSeriesRef.current = volumeSeries;

    // Crosshair bilgisi
    chart.subscribeCrosshairMove((param) => {
      if (param.point) {
        const price = param.seriesData.get(candleSeries) as any;
        if (price) {
          setHoveredPrice(price.close);
          setHoveredTime(
            param.time
              ? new Date((param.time as number) * 1000).toLocaleDateString('tr-TR')
              : null
          );
        }
      }
    });

    // Resize observer
    const resizeObserver = new ResizeObserver(() => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
        });
      }
    });
    resizeObserver.observe(chartContainerRef.current);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [height]);

  // ----------------------------------------------------------
  // Veri güncelle
  // ----------------------------------------------------------
  useEffect(() => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current || !bars.length) return;

    const candles = toTVCandles(bars);
    const volumes = toTVVolume(bars);

    candleSeriesRef.current.setData(candles as any);
    volumeSeriesRef.current.setData(volumes as any);

    // Son bara git
    chartRef.current?.timeScale().fitContent();
  }, [bars]);

  // ----------------------------------------------------------
  // Overlay göstergeleri güncelle
  // ----------------------------------------------------------
  useEffect(() => {
    if (!chartRef.current || !taData || !bars.length) return;

    const indicators = taData.indicators;
    const chart = chartRef.current;

    const addOrUpdateLine = (
      key: string,
      values: Array<{ time: Time; value: number }>,
      color: string,
      lineWidth: number = 1,
      lineStyle: LineStyle = LineStyle.Solid
    ) => {
      let series = overlaySeriesRef.current.get(key);
      if (!series) {
        series = chart.addLineSeries({
          color,
          lineWidth: lineWidth as any,
          lineStyle,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        });
        overlaySeriesRef.current.set(key, series);
      }
      series.setData(values as any);
    };

    const removeOverlay = (key: string) => {
      const series = overlaySeriesRef.current.get(key);
      if (series) {
        try { chart.removeSeries(series); } catch {}
        overlaySeriesRef.current.delete(key);
      }
    };

    const times = bars.map(
      (b) => Math.floor(new Date(b.timestamp).getTime() / 1000) as unknown as Time
    );

    // SMA 20
    if (chartSettings.showSMA20 && indicators.sma_20) {
      addOrUpdateLine(
        'sma20',
        [{ time: times[times.length - 1], value: indicators.sma_20 }],
        '#3B82F6', 1
      );
    } else removeOverlay('sma20');

    // SMA 50
    if (chartSettings.showSMA50 && indicators.sma_50) {
      addOrUpdateLine(
        'sma50',
        [{ time: times[times.length - 1], value: indicators.sma_50 }],
        '#F59E0B', 1
      );
    } else removeOverlay('sma50');

    // SMA 200
    if (chartSettings.showSMA200 && indicators.sma_200) {
      addOrUpdateLine(
        'sma200',
        [{ time: times[times.length - 1], value: indicators.sma_200 }],
        '#7C3AED', 1
      );
    } else removeOverlay('sma200');

    // VWAP
    if (chartSettings.showVWAP && indicators.vwap_daily) {
      addOrUpdateLine(
        'vwap',
        [{ time: times[times.length - 1], value: indicators.vwap_daily }],
        '#00D4FF', 1, LineStyle.Dashed
      );
    } else removeOverlay('vwap');

    // Bollinger Bands
    if (chartSettings.showBollingerBands) {
      if (indicators.bb_upper) {
        addOrUpdateLine(
          'bb_upper',
          [{ time: times[times.length - 1], value: indicators.bb_upper }],
          '#7C3AED40', 1, LineStyle.Dotted
        );
      }
      if (indicators.bb_lower) {
        addOrUpdateLine(
          'bb_lower',
          [{ time: times[times.length - 1], value: indicators.bb_lower }],
          '#7C3AED40', 1, LineStyle.Dotted
        );
      }
    } else {
      removeOverlay('bb_upper');
      removeOverlay('bb_lower');
    }

    // Destek / Direnç seviyeleri
    if (indicators.support_level) {
      addOrUpdateLine(
        'support',
        [
          { time: times[0], value: indicators.support_level },
          { time: times[times.length - 1], value: indicators.support_level },
        ],
        '#10B98150', 1, LineStyle.Dashed
      );
    }
    if (indicators.resistance_level) {
      addOrUpdateLine(
        'resistance',
        [
          { time: times[0], value: indicators.resistance_level },
          { time: times[times.length - 1], value: indicators.resistance_level },
        ],
        '#EF444450', 1, LineStyle.Dashed
      );
    }
  }, [taData, chartSettings, bars]);

  // ----------------------------------------------------------
  // Render
  // ----------------------------------------------------------
  if (isLoading) {
    return (
      <div className="flex flex-col gap-3 p-4">
        <div className="skeleton h-6 w-48" />
        <div className="skeleton rounded-xl" style={{ height }} />
      </div>
    );
  }

  const lastBar = bars[bars.length - 1];
  const prevBar = bars[bars.length - 2];
  const currentPrice = lastBar?.close_price;
  const priceChange = lastBar && prevBar
    ? ((lastBar.close_price - prevBar.close_price) / prevBar.close_price) * 100
    : 0;
  const isPositive = priceChange >= 0;

  return (
    <motion.div
      layout
      className={`flex flex-col ${isFullscreen ? 'fixed inset-0 z-50 bg-surface-1 p-4' : ''}`}
    >
      {/* Grafik başlığı */}
      <div className="flex items-center justify-between px-4 pt-4 pb-2">
        <div className="flex items-center gap-4">
          <div>
            <span className="text-text-muted text-xs uppercase tracking-widest">
              {ticker} · {timeframe.toUpperCase()}
            </span>
            {currentPrice && (
              <div className="flex items-center gap-2 mt-0.5">
                <span className="font-mono text-xl font-bold text-text-bright">
                  ${currentPrice.toFixed(2)}
                </span>
                <span
                  className={`font-mono text-sm font-medium ${
                    isPositive ? 'text-bull' : 'text-bear'
                  }`}
                >
                  {isPositive ? '+' : ''}{priceChange.toFixed(2)}%
                </span>
              </div>
            )}
          </div>

          {/* Crosshair bilgisi */}
          {hoveredPrice && (
            <div className="flex items-center gap-2 text-xs text-text-muted font-mono">
              <span>{hoveredTime}</span>
              <span className="text-accent-cyan">${hoveredPrice.toFixed(2)}</span>
            </div>
          )}
        </div>

        {/* Araç çubuğu */}
        <ChartToolbar
          isFullscreen={isFullscreen}
          onToggleFullscreen={() => setIsFullscreen(!isFullscreen)}
        />
      </div>

      {/* Gösterge Açıklamaları */}
      <div className="flex items-center gap-3 px-4 pb-2">
        {chartSettings.showSMA20 && (
          <div className="flex items-center gap-1">
            <div className="w-4 h-0.5 bg-blue-500" />
            <span className="text-[10px] text-text-muted">SMA20</span>
          </div>
        )}
        {chartSettings.showSMA50 && (
          <div className="flex items-center gap-1">
            <div className="w-4 h-0.5 bg-amber-500" />
            <span className="text-[10px] text-text-muted">SMA50</span>
          </div>
        )}
        {chartSettings.showSMA200 && (
          <div className="flex items-center gap-1">
            <div className="w-4 h-0.5 bg-purple-500" />
            <span className="text-[10px] text-text-muted">SMA200</span>
          </div>
        )}
        {chartSettings.showVWAP && (
          <div className="flex items-center gap-1">
            <div className="w-4 h-0.5 bg-accent-cyan border-dashed border-t" />
            <span className="text-[10px] text-text-muted">VWAP</span>
          </div>
        )}
        {taData?.indicators.support_level && (
          <div className="flex items-center gap-1">
            <div className="w-4 h-0.5 bg-bull/50 border-dashed border-t" />
            <span className="text-[10px] text-text-muted">
              Destek ${taData.indicators.support_level.toFixed(2)}
            </span>
          </div>
        )}
        {taData?.indicators.resistance_level && (
          <div className="flex items-center gap-1">
            <div className="w-4 h-0.5 bg-bear/50 border-dashed border-t" />
            <span className="text-[10px] text-text-muted">
              Direnç ${taData.indicators.resistance_level.toFixed(2)}
            </span>
          </div>
        )}
      </div>

      {/* Grafik */}
      <div ref={chartContainerRef} className="w-full px-2 pb-2" style={{ height }} />

      {/* Formasyonlar */}
      {taData?.patterns && taData.patterns.length > 0 && (
        <div className="flex items-center gap-2 px-4 pb-3">
          <span className="text-[10px] text-text-muted uppercase tracking-wide">Formasyonlar:</span>
          {taData.patterns.map((p) => (
            <span
              key={p}
              className={`badge text-[10px] ${p.includes('Bullish') ? 'badge-bull' : 'badge-bear'}`}
            >
              {p}
            </span>
          ))}
        </div>
      )}
    </motion.div>
  );
}

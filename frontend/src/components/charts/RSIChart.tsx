'use client';

// ============================================================
// QuantEdge AI — RSI Osilatör Grafiği
// ============================================================

import { useMemo } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ReferenceLine, ResponsiveContainer,
} from 'recharts';
import type { OHLCVBar } from '@/types';

interface RSIChartProps {
  bars: OHLCVBar[];
  rsiPeriod?: number;
  height?: number;
}

function calculateRSI(prices: number[], period = 14): number[] {
  const rsi: number[] = new Array(period).fill(NaN);

  let avgGain = 0;
  let avgLoss = 0;

  for (let i = 1; i <= period; i++) {
    const change = prices[i] - prices[i - 1];
    if (change > 0) avgGain += change;
    else avgLoss += Math.abs(change);
  }

  avgGain /= period;
  avgLoss /= period;

  const firstRS = avgLoss === 0 ? 100 : avgGain / avgLoss;
  rsi.push(100 - 100 / (1 + firstRS));

  for (let i = period + 1; i < prices.length; i++) {
    const change = prices[i] - prices[i - 1];
    const gain = change > 0 ? change : 0;
    const loss = change < 0 ? Math.abs(change) : 0;

    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;

    const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
    rsi.push(100 - 100 / (1 + rs));
  }

  return rsi;
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  const rsi = payload[0]?.value;
  if (rsi === undefined || isNaN(rsi)) return null;

  return (
    <div className="bg-surface-3 border border-border-default rounded-lg px-3 py-2 text-xs">
      <p className="text-text-muted mb-1">{label}</p>
      <p className={`font-mono font-bold ${
        rsi < 30 ? 'text-bull' : rsi > 70 ? 'text-bear' : 'text-text-primary'
      }`}>
        RSI: {rsi.toFixed(1)}
      </p>
    </div>
  );
};

export function RSIChart({ bars, rsiPeriod = 14, height = 120 }: RSIChartProps) {
  const data = useMemo(() => {
    if (!bars?.length) return [];
    const prices = bars.map(b => b.close_price);
    const rsiValues = calculateRSI(prices, rsiPeriod);

    return bars.map((bar, i) => ({
      date: new Date(bar.timestamp).toLocaleDateString('tr-TR', { month: 'short', day: 'numeric' }),
      rsi: isNaN(rsiValues[i]) ? null : parseFloat(rsiValues[i].toFixed(2)),
    })).filter(d => d.rsi !== null).slice(-120);
  }, [bars, rsiPeriod]);

  const lastRSI = data.at(-1)?.rsi ?? 50;
  const rsiColor = lastRSI < 30 ? '#10B981' : lastRSI > 70 ? '#EF4444' : '#3B82F6';

  return (
    <div>
      {/* Başlık */}
      <div className="flex items-center justify-between px-1 mb-1">
        <span className="text-[10px] text-text-muted uppercase tracking-wide font-mono">
          RSI ({rsiPeriod})
        </span>
        <span className={`text-xs font-mono font-bold`} style={{ color: rsiColor }}>
          {lastRSI.toFixed(1)}
          {lastRSI < 30 && <span className="ml-1 text-[9px]">AŞIRI SATIM</span>}
          {lastRSI > 70 && <span className="ml-1 text-[9px]">AŞIRI ALIM</span>}
        </span>
      </div>

      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1E2535" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fill: '#4B5980', fontSize: 9 }}
            tickLine={false}
            axisLine={false}
            interval={Math.floor(data.length / 6)}
          />
          <YAxis
            domain={[0, 100]}
            ticks={[0, 30, 50, 70, 100]}
            tick={{ fill: '#4B5980', fontSize: 9 }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip content={<CustomTooltip />} />

          {/* Aşırı alım/satım bölgeleri */}
          <ReferenceLine y={70} stroke="#EF444440" strokeDasharray="4 4" />
          <ReferenceLine y={30} stroke="#10B98140" strokeDasharray="4 4" />
          <ReferenceLine y={50} stroke="#37425820" />

          <Area
            type="monotone"
            dataKey="rsi"
            stroke={rsiColor}
            strokeWidth={1.5}
            fill={`${rsiColor}15`}
            dot={false}
            activeDot={{ r: 3, fill: rsiColor }}
          />
        </AreaChart>
      </ResponsiveContainer>

      {/* Etiketler */}
      <div className="flex justify-between px-1 mt-0.5">
        <span className="text-[9px] text-bear/60">Aşırı Alım (70)</span>
        <span className="text-[9px] text-bull/60">Aşırı Satım (30)</span>
      </div>
    </div>
  );
}


// ============================================================
// MACD Grafiği
// ============================================================

interface MACDChartProps {
  bars: OHLCVBar[];
  fastPeriod?: number;
  slowPeriod?: number;
  signalPeriod?: number;
  height?: number;
}

function calculateEMA(prices: number[], period: number): number[] {
  const ema: number[] = [];
  const k = 2 / (period + 1);

  // İlk EMA = basit ortalama
  let sum = 0;
  for (let i = 0; i < period; i++) {
    sum += prices[i];
    ema.push(NaN);
  }
  ema[period - 1] = sum / period;

  for (let i = period; i < prices.length; i++) {
    ema.push(prices[i] * k + ema[ema.length - 1] * (1 - k));
  }

  return ema;
}

function calculateMACD(
  prices: number[],
  fast = 12, slow = 26, signal = 9
): { macd: number[]; signalLine: number[]; histogram: number[] } {
  const emaFast = calculateEMA(prices, fast);
  const emaSlow = calculateEMA(prices, slow);

  const macd = emaFast.map((f, i) =>
    isNaN(f) || isNaN(emaSlow[i]) ? NaN : f - emaSlow[i]
  );

  const validMacd = macd.filter(v => !isNaN(v));
  const rawSignal = calculateEMA(validMacd, signal);

  const signalLine: number[] = new Array(macd.length - validMacd.length).fill(NaN);
  rawSignal.forEach(v => signalLine.push(v));

  const histogram = macd.map((m, i) =>
    isNaN(m) || isNaN(signalLine[i]) ? NaN : m - signalLine[i]
  );

  return { macd, signalLine, histogram };
}

const MACDTooltip = ({ active, payload }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-surface-3 border border-border-default rounded-lg px-3 py-2 text-xs space-y-1">
      {payload.map((p: any) => (
        <div key={p.name} className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full" style={{ backgroundColor: p.color }} />
          <span className="text-text-muted">{p.name}:</span>
          <span className="font-mono font-bold" style={{ color: p.color }}>
            {typeof p.value === 'number' ? p.value.toFixed(3) : '—'}
          </span>
        </div>
      ))}
    </div>
  );
};

export function MACDChart({
  bars,
  fastPeriod = 12,
  slowPeriod = 26,
  signalPeriod = 9,
  height = 130,
}: MACDChartProps) {
  const data = useMemo(() => {
    if (!bars?.length) return [];
    const prices = bars.map(b => b.close_price);
    const { macd, signalLine, histogram } = calculateMACD(
      prices, fastPeriod, slowPeriod, signalPeriod
    );

    return bars.map((bar, i) => ({
      date: new Date(bar.timestamp).toLocaleDateString('tr-TR', { month: 'short', day: 'numeric' }),
      macd:      isNaN(macd[i])       ? null : parseFloat(macd[i].toFixed(4)),
      signal:    isNaN(signalLine[i]) ? null : parseFloat(signalLine[i].toFixed(4)),
      histogram: isNaN(histogram[i])  ? null : parseFloat(histogram[i].toFixed(4)),
    })).filter(d => d.macd !== null).slice(-120);
  }, [bars, fastPeriod, slowPeriod, signalPeriod]);

  const last = data.at(-1);
  const isBullish = (last?.macd ?? 0) > (last?.signal ?? 0);

  return (
    <div>
      {/* Başlık */}
      <div className="flex items-center justify-between px-1 mb-1">
        <span className="text-[10px] text-text-muted uppercase tracking-wide font-mono">
          MACD ({fastPeriod},{slowPeriod},{signalPeriod})
        </span>
        <div className="flex items-center gap-3">
          <span className="text-[10px] font-mono text-blue-400">
            MACD: {last?.macd?.toFixed(3) ?? '—'}
          </span>
          <span className="text-[10px] font-mono text-orange-400">
            SIG: {last?.signal?.toFixed(3) ?? '—'}
          </span>
          <span className={`text-[9px] font-semibold px-1.5 py-0.5 rounded
            ${isBullish ? 'bg-bull/10 text-bull' : 'bg-bear/10 text-bear'}`}>
            {isBullish ? '↑ Bullish' : '↓ Bearish'}
          </span>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1E2535" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fill: '#4B5980', fontSize: 9 }}
            tickLine={false}
            axisLine={false}
            interval={Math.floor(data.length / 6)}
          />
          <YAxis
            tick={{ fill: '#4B5980', fontSize: 9 }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip content={<MACDTooltip />} />
          <ReferenceLine y={0} stroke="#37425850" />

          {/* Histogram — pozitif yeşil, negatif kırmızı */}
          {data.map((d, i) => null)}
          <Area
            type="monotone"
            dataKey="histogram"
            name="Histogram"
            stroke="transparent"
            fill="#3B82F620"
          />

          {/* MACD çizgisi */}
          <Area
            type="monotone"
            dataKey="macd"
            name="MACD"
            stroke="#3B82F6"
            strokeWidth={1.5}
            fill="transparent"
            dot={false}
            activeDot={{ r: 3 }}
          />

          {/* Sinyal çizgisi */}
          <Area
            type="monotone"
            dataKey="signal"
            name="Sinyal"
            stroke="#F97316"
            strokeWidth={1.5}
            strokeDasharray="4 2"
            fill="transparent"
            dot={false}
            activeDot={{ r: 3 }}
          />
        </AreaChart>
      </ResponsiveContainer>

      {/* Gösterge */}
      <div className="flex items-center gap-4 px-1 mt-0.5">
        <div className="flex items-center gap-1">
          <div className="w-3 h-0.5 bg-blue-500" />
          <span className="text-[9px] text-text-muted">MACD</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-0.5 bg-orange-400 border-dashed border-t" />
          <span className="text-[9px] text-text-muted">Sinyal</span>
        </div>
      </div>
    </div>
  );
}

'use client';

// ============================================================
// QuantEdge AI — Tahmin Paneli
// ============================================================

import { useState } from 'react';
import { motion } from 'framer-motion';
import {
  TrendingUp, TrendingDown, Minus, AlertTriangle,
  RefreshCw, Info, ChevronDown, ChevronUp,
} from 'lucide-react';
import { api, formatPrice, formatPct } from '@/lib/api';
import { usePredictionStore, useChartStore } from '@/store';
import type { PredictionResponse, Timeframe, Direction } from '@/types';
import EventBadge from '@/components/dashboard/EventBadge';

const TIMEFRAMES: { value: Timeframe; label: string; desc: string }[] = [
  { value: '1d', label: '1 Gün',   desc: 'Kısa vadeli' },
  { value: '1w', label: '1 Hafta', desc: 'Orta-kısa' },
  { value: '1mo', label: '1 Ay',   desc: 'Orta vade' },
  { value: '3mo', label: '3 Ay',   desc: 'Orta-uzun' },
  { value: '1y',  label: '1 Yıl',  desc: 'Uzun vade' },
];

interface PredictionPanelProps {
  ticker: string;
}

export function PredictionPanel({ ticker }: PredictionPanelProps) {
  const [selectedTf, setSelectedTf] = useState<Timeframe>('1d');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showDetails, setShowDetails] = useState(false);

  const { predictions, setPrediction } = usePredictionStore();
  const predKey = `${ticker}:${selectedTf}`;
  const prediction = predictions[predKey];

  const fetchPrediction = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await api.getPrediction({
        ticker,
        timeframe: selectedTf,
        include_technical: true,
        include_sentiment: true,
        include_fundamental: true,
        include_macro: true,
      });
      setPrediction(predKey, result);
    } catch (e: any) {
      setError(e.message || 'Tahmin alınamadı.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 stagger">

      {/* Sol: Timeframe seçici + Tahmin butonu */}
      <div className="card p-4 flex flex-col gap-4">
        <h3 className="text-sm font-semibold text-text-bright flex items-center gap-2">
          <span className="text-lg">🎯</span> Tahmin Oluştur
        </h3>

        <div className="space-y-2">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf.value}
              onClick={() => setSelectedTf(tf.value)}
              className={`
                w-full flex items-center justify-between px-3 py-2.5 rounded-lg
                border transition-all text-sm
                ${selectedTf === tf.value
                  ? 'bg-accent-cyan/10 border-accent-cyan/40 text-accent-cyan'
                  : 'bg-surface-3 border-border-subtle text-text-secondary hover:border-border-default hover:text-text-primary'}
              `}
            >
              <div className="flex flex-col items-start">
                <span className="font-semibold">{tf.label}</span>
                <span className="text-[10px] opacity-60">{tf.desc}</span>
              </div>
              {predictions[`${ticker}:${tf.value}`] && (
                <DirectionBadge
                  direction={predictions[`${ticker}:${tf.value}`].direction}
                  small
                />
              )}
            </button>
          ))}
        </div>

        <button
          onClick={fetchPrediction}
          disabled={isLoading}
          className="btn-primary w-full mt-auto"
        >
          {isLoading ? (
            <><RefreshCw size={14} className="animate-spin" /> Hesaplanıyor...</>
          ) : (
            <><span>⚡</span> {prediction ? 'Yenile' : 'Tahmin Al'}</>
          )}
        </button>

        {error && (
          <p className="text-xs text-bear flex items-center gap-1">
            <AlertTriangle size={12} /> {error}
          </p>
        )}

        {/* Ağırlık bilgisi */}
        <WeightInfo timeframe={selectedTf} />
      </div>

      {/* Orta: Ana tahmin */}
      <div className="lg:col-span-2 flex flex-col gap-4">
        {prediction ? (
          <>
            <PredictionCard prediction={prediction} />

            {/* Sinyal metrikler */}
            <SignalMetrics prediction={prediction} />

            {/* Detaylar toggle */}
            <button
              onClick={() => setShowDetails(!showDetails)}
              className="flex items-center gap-1 text-xs text-text-muted hover:text-text-secondary transition-colors"
            >
              {showDetails ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              {showDetails ? 'Detayları Gizle' : 'Model Detayları'}
            </button>

            {showDetails && <ModelDetails prediction={prediction} />}
          </>
        ) : (
          <EmptyPrediction ticker={ticker} onFetch={fetchPrediction} />
        )}
      </div>
    </div>
  );
}

// ----------------------------------------------------------
// Ana Tahmin Kartı
// ----------------------------------------------------------

function PredictionCard({ prediction }: { prediction: PredictionResponse }) {
  const isUp = prediction.direction === 'up';
  const isDown = prediction.direction === 'down';
  const returnPct = prediction.predicted_return_pct || 0;

  return (
    <div
      className={`
        card p-5 border-l-4 relative overflow-hidden
        ${isUp ? 'border-l-bull bg-bull-gradient' : isDown ? 'border-l-bear bg-bear-gradient' : 'border-l-neutral'}
      `}
    >
      {/* Arka plan efekti */}
      <div className={`absolute top-0 right-0 w-48 h-48 rounded-full blur-3xl opacity-5
        ${isUp ? 'bg-bull' : isDown ? 'bg-bear' : 'bg-neutral'}`} />

      <div className="relative z-10">
        <div className="flex items-start justify-between mb-4">
          <div>
            <p className="text-xs text-text-muted mb-1">
              {prediction.ticker} · {prediction.timeframe.toUpperCase()} tahmini
            </p>
            <div className="flex items-center gap-3">
              <DirectionBadge direction={prediction.direction} />
              <span className="text-xs text-text-muted">
                {(prediction.direction_confidence * 100).toFixed(0)}% güven
              </span>
            </div>
          </div>

          {prediction.anomaly_detected && (
            <div className="flex items-center gap-1 bg-amber-500/10 border border-amber-500/30 rounded-lg px-2 py-1">
              <AlertTriangle size={12} className="text-amber-400" />
              <span className="text-xs text-amber-400">Anomali</span>
            </div>
          )}
        </div>

        <div className="grid grid-cols-3 gap-4">
          {/* Mevcut fiyat */}
          <div>
            <p className="text-[10px] text-text-muted uppercase tracking-wide mb-1">Mevcut</p>
            <p className="font-mono text-lg font-bold text-text-bright">
              {formatPrice(prediction.current_price)}
            </p>
          </div>

          {/* Tahmin fiyat */}
          <div>
            <p className="text-[10px] text-text-muted uppercase tracking-wide mb-1">Tahmin</p>
            <p className={`font-mono text-lg font-bold ${isUp ? 'text-bull' : isDown ? 'text-bear' : 'text-text-primary'}`}>
              {formatPrice(prediction.predicted_price)}
            </p>
          </div>

          {/* Beklenen getiri */}
          <div>
            <p className="text-[10px] text-text-muted uppercase tracking-wide mb-1">Getiri</p>
            <p className={`font-mono text-lg font-bold ${returnPct >= 0 ? 'text-bull' : 'text-bear'}`}>
              {formatPct(returnPct)}
            </p>
          </div>
        </div>

        {/* Güven Aralığı */}
        {prediction.lower_bound && prediction.upper_bound && (
          <div className="mt-4 p-3 bg-surface-0/50 rounded-lg">
            <p className="text-[10px] text-text-muted mb-2">%90 Güven Aralığı</p>
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm text-bear">{formatPrice(prediction.lower_bound)}</span>
              <div className="flex-1 relative h-2 bg-surface-4 rounded-full">
                <div className="absolute inset-y-0 bg-accent-cyan/30 rounded-full"
                  style={{
                    left: '10%', right: '10%',
                  }} />
                <div
                  className={`absolute top-1/2 -translate-y-1/2 w-2 h-4 rounded-full
                    ${isUp ? 'bg-bull' : isDown ? 'bg-bear' : 'bg-accent-cyan'}`}
                  style={{ left: '50%' }}
                />
              </div>
              <span className="font-mono text-sm text-bull">{formatPrice(prediction.upper_bound)}</span>
            </div>
            <div className="flex justify-between mt-1">
              <span className="text-[10px] text-text-muted">Alt Sınır</span>
              <span className="text-[10px] text-text-muted">Üst Sınır</span>
            </div>
          </div>
        )}

        <EventBadge eventContext={prediction.event_context} />

        {/* Anomali açıklama */}
        {prediction.anomaly_detected && prediction.anomaly_description && (
          <div className="mt-3 p-3 bg-amber-500/5 border border-amber-500/20 rounded-lg">
            <p className="text-xs text-amber-400">{prediction.anomaly_description}</p>
          </div>
        )}

        {/* Risk seviyesi */}
        <div className="mt-4 flex items-center justify-between">
          <RiskBadge level={prediction.risk_level} />
          <span className="text-[10px] text-text-muted font-mono">
            v{prediction.model_version}
          </span>
        </div>
      </div>
    </div>
  );
}

// ----------------------------------------------------------
// Sinyal Metrikleri
// ----------------------------------------------------------

function SignalMetrics({ prediction }: { prediction: PredictionResponse }) {
  const metrics = [
    { label: 'Teknik',    value: prediction.technical_score,    icon: '📊' },
    { label: 'Sentiment', value: prediction.sentiment_score,    icon: '💬' },
    { label: 'Makro',     value: prediction.macro_score,        icon: '🌍' },
  ];

  const fundScore = prediction.fundamental_score;

  return (
    <div className="card p-4">
      <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-3">
        Sinyal Güçleri
      </h4>
      <div className="space-y-3">
        {metrics.map((m) => (
          <SignalBar key={m.label} label={m.label} icon={m.icon} value={m.value} type="bipolar" />
        ))}
        {fundScore !== undefined && (
          <SignalBar label="Temel Analiz" icon="📋" value={fundScore} type="unipolar" max={100} />
        )}
      </div>
    </div>
  );
}

function SignalBar({
  label, icon, value, type, max = 1,
}: {
  label: string; icon: string; value?: number; type: 'bipolar' | 'unipolar'; max?: number;
}) {
  if (value === undefined || value === null) return null;

  const pct = type === 'bipolar'
    ? ((value + 1) / 2) * 100     // -1…1 → 0…100
    : (value / max) * 100;        // 0…max → 0…100

  const color = type === 'bipolar'
    ? (value > 0.1 ? '#10B981' : value < -0.1 ? '#EF4444' : '#6B7280')
    : (value > 60 ? '#10B981' : value > 40 ? '#F59E0B' : '#EF4444');

  return (
    <div className="flex items-center gap-3">
      <span className="text-sm w-4">{icon}</span>
      <span className="text-xs text-text-secondary w-20">{label}</span>
      <div className="flex-1 score-bar">
        {type === 'bipolar' && (
          <div className="absolute left-1/2 top-0 bottom-0 w-px bg-border-strong" />
        )}
        <motion.div
          className="score-bar-fill"
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.8, ease: 'easeOut' }}
          style={{ backgroundColor: color }}
        />
      </div>
      <span className="text-xs font-mono text-text-secondary w-12 text-right">
        {type === 'bipolar' ? (value >= 0 ? '+' : '') + value.toFixed(2) : value.toFixed(0)}
      </span>
    </div>
  );
}

// ----------------------------------------------------------
// Model Detayları
// ----------------------------------------------------------

function ModelDetails({ prediction }: { prediction: PredictionResponse }) {
  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: 'auto' }}
      exit={{ opacity: 0, height: 0 }}
      className="card p-4 space-y-4"
    >
      <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wide">
        Model Katkıları
      </h4>

      {prediction.model_contributions && (
        <div className="grid grid-cols-3 gap-3">
          {Object.entries(prediction.model_contributions).map(([model, pred]) => (
            <div key={model} className="metric-box">
              <span className="metric-label">{model.toUpperCase()}</span>
              <span className={`metric-value text-sm ${(pred as number) >= 0 ? 'text-bull' : 'text-bear'}`}>
                {((pred as number) * 100).toFixed(2)}%
              </span>
            </div>
          ))}
        </div>
      )}

      {prediction.ensemble_weights && (
        <div>
          <p className="text-[10px] text-text-muted mb-2">Ensemble Ağırlıkları</p>
          <div className="flex gap-2">
            {Object.entries(prediction.ensemble_weights).map(([model, weight]) => (
              <div key={model}
                className="flex-1 bg-surface-3 rounded-lg p-2 text-center border border-border-subtle"
              >
                <p className="text-[10px] text-text-muted">{model}</p>
                <p className="text-xs font-mono font-bold text-accent-cyan mt-0.5">
                  {((weight as number) * 100).toFixed(0)}%
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {prediction.explanation && (
        <div className="p-3 bg-surface-3 rounded-lg border border-border-subtle">
          <p className="text-xs text-text-secondary leading-relaxed">
            {prediction.explanation}
          </p>
        </div>
      )}

      {/* Disclaimer */}
      <div className="flex items-start gap-2 p-3 bg-amber-500/5 border border-amber-500/10 rounded-lg">
        <Info size={12} className="text-amber-400 mt-0.5 flex-shrink-0" />
        <p className="text-[10px] text-amber-400/80 leading-relaxed">
          {prediction.disclaimer}
        </p>
      </div>
    </motion.div>
  );
}

// ----------------------------------------------------------
// Yardımcı Bileşenler
// ----------------------------------------------------------

function DirectionBadge({ direction, small }: { direction: Direction; small?: boolean }) {
  const config = {
    up:       { icon: TrendingUp,   color: 'badge-bull',    label: 'Yükseliş' },
    down:     { icon: TrendingDown, color: 'badge-bear',    label: 'Düşüş'    },
    sideways: { icon: Minus,        color: 'badge-neutral', label: 'Yatay'    },
  };
  const { icon: Icon, color, label } = config[direction] || config.sideways;

  return (
    <span className={`${color} ${small ? 'text-[9px] px-1.5 py-0.5' : ''}`}>
      <Icon size={small ? 10 : 12} />
      {!small && label}
    </span>
  );
}

function RiskBadge({ level }: { level: string }) {
  const config = {
    low:     { color: 'text-bull bg-bull/10 border-bull/20', label: 'Düşük Risk' },
    medium:  { color: 'text-amber-400 bg-amber-400/10 border-amber-400/20', label: 'Orta Risk' },
    high:    { color: 'text-bear bg-bear/10 border-bear/20', label: 'Yüksek Risk' },
    extreme: { color: 'text-red-400 bg-red-400/20 border-red-400/40', label: 'AŞIRI RİSK' },
  };
  const { color, label } = config[level as keyof typeof config] || config.medium;

  return (
    <span className={`badge border ${color} text-[10px] font-semibold`}>
      {level === 'extreme' && <AlertTriangle size={10} />}
      {label}
    </span>
  );
}

function WeightInfo({ timeframe }: { timeframe: Timeframe }) {
  const weights = {
    '1d':  { teknik: 35, sentiment: 30, temel: 20, makro: 15 },
    '1w':  { teknik: 30, sentiment: 25, temel: 25, makro: 20 },
    '1mo': { teknik: 20, sentiment: 15, temel: 35, makro: 30 },
    '3mo': { teknik: 16, sentiment: 11, temel: 38, makro: 36 },
    '1y':  { teknik: 10, sentiment:  5, temel: 45, makro: 40 },
  };
  const w = weights[timeframe];

  return (
    <div className="p-3 bg-surface-3 rounded-lg border border-border-subtle">
      <p className="text-[10px] text-text-muted mb-2">Ağırlık Dağılımı</p>
      <div className="space-y-1.5">
        {Object.entries(w).map(([key, val]) => (
          <div key={key} className="flex items-center gap-2">
            <span className="text-[10px] text-text-muted w-16 capitalize">{key}</span>
            <div className="flex-1 score-bar">
              <div className="score-bar-fill bg-accent-cyan" style={{ width: `${val}%` }} />
            </div>
            <span className="text-[10px] font-mono text-text-muted">{val}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function EmptyPrediction({ ticker, onFetch }: { ticker: string; onFetch: () => void }) {
  return (
    <div className="card p-8 flex flex-col items-center justify-center gap-4 text-center min-h-[300px]">
      <div className="text-4xl">🎯</div>
      <div>
        <p className="text-text-primary font-semibold">{ticker} için tahmin hazır değil</p>
        <p className="text-sm text-text-muted mt-1">
          Zaman dilimini seçin ve tahmin alın
        </p>
      </div>
      <button onClick={onFetch} className="btn-primary">
        <span>⚡</span> Tahmin Al
      </button>
    </div>
  );
}

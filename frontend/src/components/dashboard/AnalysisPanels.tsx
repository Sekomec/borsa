'use client';

// ============================================================
// QuantEdge AI — Analiz Panelleri
// Technical | Sentiment | Macro | Fundamental
// ============================================================

import { motion } from 'framer-motion';
import {
  TrendingUp, TrendingDown, Minus, MessageSquare,
  Globe, BarChart2, AlertTriangle,
} from 'lucide-react';
import {
  RadarChart, PolarGrid, PolarAngleAxis,
  Radar, ResponsiveContainer, AreaChart, Area,
  XAxis, YAxis, Tooltip, CartesianGrid,
} from 'recharts';
import {
  useTechnicalAnalysis, useSentiment, useFundamental,
  useMacroSnapshot, formatPrice, formatPct, formatMarketCap,
} from '@/lib/api';
import { useChartStore } from '@/store';
import type { MacroSnapshot } from '@/types';

// ----------------------------------------------------------
// TEKNİK ANALİZ PANELİ
// ----------------------------------------------------------

export function TechnicalPanel({ ticker }: { ticker: string }) {
  const { timeframe } = useChartStore();
  const { data: ta, isLoading } = useTechnicalAnalysis(ticker, timeframe as any);

  if (isLoading) return <PanelSkeleton rows={8} />;
  if (!ta) return <EmptyPanel message="Teknik analiz verisi yüklenemedi." />;

  const ind = ta.indicators;
  const sig = ta.signals;
  const composite = sig.composite_signal || 0;

  // Radar grafik verisi
  const radarData = [
    { subject: 'RSI',     value: ind.rsi_14 || 50 },
    { subject: 'MACD',    value: composite >= 0 ? 70 : 30 },
    { subject: 'BB',      value: ((ind.bb_pct_b || 0.5) * 100) },
    { subject: 'Hacim',   value: Math.min(100, (ind.volume_ratio || 1) * 50) },
    { subject: 'Trend',   value: ind.sma_20 && ind.sma_50 ? (ind.sma_20 > ind.sma_50 ? 70 : 30) : 50 },
    { subject: 'ADX',     value: ind.adx || 25 },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 stagger">

      {/* Bileşik Sinyal Göstergesi */}
      <div className="card p-4 flex flex-col items-center gap-3">
        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wide self-start">
          Bileşik Sinyal
        </h3>
        <CompositeSignalGauge value={composite} label={sig.signal_summary} />
      </div>

      {/* Radar Grafik */}
      <div className="card p-4">
        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-3">
          Gösterge Radar
        </h3>
        <ResponsiveContainer width="100%" height={180}>
          <RadarChart data={radarData}>
            <PolarGrid stroke="#1E2535" />
            <PolarAngleAxis dataKey="subject" tick={{ fill: '#4B5980', fontSize: 10 }} />
            <Radar
              name="Değer"
              dataKey="value"
              stroke="#00D4FF"
              fill="#00D4FF"
              fillOpacity={0.15}
              strokeWidth={1.5}
            />
          </RadarChart>
        </ResponsiveContainer>
      </div>

      {/* Göstergeler Grid */}
      <div className="card p-4">
        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-3">
          Göstergeler
        </h3>
        <div className="space-y-2">
          <IndicatorRow label="RSI (14)" value={ind.rsi_14} suffix="" type="rsi" />
          <IndicatorRow label="MACD" value={ind.macd} suffix="" type="macd" />
          <IndicatorRow label="MACD Sinyal" value={ind.macd_signal} suffix="" type="neutral" />
          <IndicatorRow label="ATR (14)" value={ind.atr_14} prefix="$" type="neutral" />
          <IndicatorRow label="OBV" value={ind.obv} type="neutral" large />
          <IndicatorRow label="Volume Oran" value={ind.volume_ratio} suffix="x" type="volume" />
          <IndicatorRow label="VWAP" value={ind.vwap_daily} prefix="$" type="neutral" />
        </div>
      </div>

      {/* Bollinger Bands */}
      <div className="card p-4">
        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-3">
          Bollinger Bands
        </h3>
        {ind.bb_upper && ind.bb_lower && ind.bb_middle ? (
          <div className="space-y-3">
            <div className="flex justify-between text-xs">
              <span className="text-text-muted">Üst Band</span>
              <span className="font-mono text-text-primary">{formatPrice(ind.bb_upper)}</span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-text-muted">Orta (SMA20)</span>
              <span className="font-mono text-accent-cyan">{formatPrice(ind.bb_middle)}</span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-text-muted">Alt Band</span>
              <span className="font-mono text-text-primary">{formatPrice(ind.bb_lower)}</span>
            </div>
            {ind.bb_pct_b !== undefined && (
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-text-muted">%B Pozisyon</span>
                  <span className="font-mono">{(ind.bb_pct_b * 100).toFixed(1)}%</span>
                </div>
                <div className="score-bar">
                  <motion.div
                    className="score-bar-fill"
                    initial={{ width: 0 }}
                    animate={{ width: `${ind.bb_pct_b * 100}%` }}
                    style={{
                      backgroundColor: ind.bb_pct_b < 0.2 ? '#10B981' : ind.bb_pct_b > 0.8 ? '#EF4444' : '#00D4FF',
                    }}
                  />
                </div>
              </div>
            )}
          </div>
        ) : (
          <p className="text-xs text-text-muted">BB verisi mevcut değil</p>
        )}
      </div>

      {/* Destek / Direnç */}
      <div className="card p-4">
        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-3">
          Destek / Direnç
        </h3>
        {ind.support_level || ind.resistance_level ? (
          <div className="space-y-3">
            {ind.resistance_level && (
              <div className="p-2 bg-bear/5 border border-bear/20 rounded-lg">
                <p className="text-[10px] text-text-muted">Direnç</p>
                <p className="font-mono font-bold text-bear">{formatPrice(ind.resistance_level)}</p>
              </div>
            )}
            {ind.support_level && (
              <div className="p-2 bg-bull/5 border border-bull/20 rounded-lg">
                <p className="text-[10px] text-text-muted">Destek</p>
                <p className="font-mono font-bold text-bull">{formatPrice(ind.support_level)}</p>
              </div>
            )}
          </div>
        ) : (
          <p className="text-xs text-text-muted">Destek/Direnç hesaplanıyor...</p>
        )}
      </div>

      {/* Formasyonlar */}
      <div className="card p-4">
        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-3">
          Formasyonlar
        </h3>
        {ta.patterns.length > 0 ? (
          <div className="space-y-1.5">
            {ta.patterns.map((p) => (
              <div key={p}
                className={`flex items-center gap-2 text-xs p-2 rounded-lg
                  ${p.includes('Bullish') ? 'bg-bull/5 text-bull border border-bull/20' : 'bg-bear/5 text-bear border border-bear/20'}`}
              >
                {p.includes('Bullish') ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                {p}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-text-muted">Belirgin formasyon bulunamadı.</p>
        )}
      </div>
    </div>
  );
}

// ----------------------------------------------------------
// SENTİMENT PANELİ
// ----------------------------------------------------------

export function SentimentPanel({ ticker }: { ticker: string }) {
  const { data: sentiment, isLoading } = useSentiment(ticker);
  if (isLoading) return <PanelSkeleton rows={6} />;
  if (!sentiment) return <EmptyPanel message="Sentiment verisi yüklenemedi." />;

  const score = sentiment.overall_score;
  const isPositive = score > 0.1;
  const isNegative = score < -0.1;

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 stagger">

      {/* Özet */}
      <div className="card p-5">
        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-4">
          Piyasa Duyarlılığı
        </h3>
        <div className="flex items-center gap-4 mb-4">
          <div className={`text-4xl font-display font-bold
            ${isPositive ? 'text-bull' : isNegative ? 'text-bear' : 'text-text-secondary'}`}>
            {isPositive ? '📈' : isNegative ? '📉' : '😐'}
          </div>
          <div>
            <p className={`text-lg font-bold ${isPositive ? 'text-bull' : isNegative ? 'text-bear' : 'text-text-secondary'}`}>
              {sentiment.sentiment_label}
            </p>
            <p className="font-mono text-sm text-text-muted">
              Skor: {score >= 0 ? '+' : ''}{score.toFixed(3)}
            </p>
          </div>
        </div>

        {/* Sentiment meter */}
        <div>
          <div className="signal-bar h-3 rounded-full mb-2" />
          <div
            className="w-3 h-3 rounded-full bg-white border-2 border-surface-0 relative -mt-5 transition-all duration-700"
            style={{ marginLeft: `${((score + 1) / 2) * 100}%`, transform: 'translateX(-50%)' }}
          />
          <div className="flex justify-between text-[10px] text-text-muted mt-2">
            <span>Çok Bearish</span><span>Nötr</span><span>Çok Bullish</span>
          </div>
        </div>
      </div>

      {/* Kaynak Skorları */}
      <div className="card p-5">
        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-4">
          Kaynak Bazlı Skorlar
        </h3>
        <div className="space-y-3">
          {[
            { label: 'Haberler', value: sentiment.news_score, icon: '📰', weight: '40%' },
            { label: 'Reddit', value: sentiment.reddit_score, icon: '🤖', weight: '35%' },
            { label: 'StockTwits', value: sentiment.stocktwits_score, icon: '💹', weight: '25%' },
          ].map((src) => src.value !== null && src.value !== undefined ? (
            <div key={src.label} className="flex items-center gap-3">
              <span>{src.icon}</span>
              <div className="flex-1">
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-text-secondary">{src.label}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-text-muted text-[10px]">ağırlık: {src.weight}</span>
                    <span className={`font-mono font-medium
                      ${(src.value || 0) > 0.1 ? 'text-bull' : (src.value || 0) < -0.1 ? 'text-bear' : 'text-text-secondary'}`}>
                      {(src.value || 0) >= 0 ? '+' : ''}{(src.value || 0).toFixed(3)}
                    </span>
                  </div>
                </div>
                <div className="score-bar">
                  <div className="absolute left-1/2 top-0 bottom-0 w-px bg-border-strong" />
                  <motion.div
                    className="score-bar-fill"
                    initial={{ width: 0 }}
                    animate={{ width: `${((src.value || 0) + 1) / 2 * 100}%` }}
                    style={{ backgroundColor: (src.value || 0) > 0 ? '#10B981' : '#EF4444' }}
                  />
                </div>
              </div>
            </div>
          ) : null)}
        </div>

        <div className="mt-4 flex items-center gap-4 text-xs text-text-muted">
          {sentiment.total_mentions && (
            <span>💬 {sentiment.total_mentions.toLocaleString()} bahsedilme</span>
          )}
          {sentiment.news_article_count && (
            <span>📰 {sentiment.news_article_count} haber</span>
          )}
        </div>
      </div>

      {/* Haberler */}
      {sentiment.top_headlines && sentiment.top_headlines.length > 0 && (
        <div className="card p-4 md:col-span-2">
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-3">
            Son Haberler
          </h3>
          <div className="space-y-2">
            {sentiment.top_headlines.slice(0, 5).map((h, i) => (
              <div key={i} className="flex items-start gap-3 p-2 hover:bg-surface-3 rounded-lg transition-colors">
                <span className="text-text-muted text-xs mt-0.5">{i + 1}.</span>
                <div className="flex-1 min-w-0">
                  <a href={h.url} target="_blank" rel="noopener noreferrer"
                    className="text-xs text-text-primary hover:text-accent-cyan transition-colors line-clamp-2">
                    {h.title}
                  </a>
                  <p className="text-[10px] text-text-muted mt-0.5">
                    {h.source} · {h.published_at ? new Date(h.published_at).toLocaleDateString('tr-TR') : ''}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ----------------------------------------------------------
// MAKRO PANELİ
// ----------------------------------------------------------

export function MacroPanel() {
  const { data: macro, isLoading } = useMacroSnapshot();
  if (isLoading) return <PanelSkeleton rows={10} />;
  if (!macro) return <EmptyPanel message="Makro veri yüklenemedi." />;

  const metrics = [
    { label: 'FED Faiz Oranı',     value: macro.fed_rate,           suffix: '%', desc: 'Federal Funds Rate' },
    { label: '10Y Hazine',          value: macro.us_10y_yield,       suffix: '%', desc: 'ABD 10 Yıllık Tahvil' },
    { label: '2Y Hazine',           value: macro.us_2y_yield,        suffix: '%', desc: 'ABD 2 Yıllık Tahvil' },
    { label: 'Yield Spread',        value: macro.yield_curve_spread, suffix: '%', desc: '10Y - 2Y' },
    { label: 'VIX',                 value: macro.vix,                suffix: '',  desc: 'Korku Endeksi' },
    { label: 'DXY',                 value: macro.dxy,                suffix: '',  desc: 'Dolar Endeksi' },
    { label: 'TÜFE (YoY)',          value: macro.cpi_yoy_pct,        suffix: '%', desc: 'Enflasyon' },
    { label: 'İşsizlik',            value: macro.unemployment_rate,  suffix: '%', desc: 'ABD İşsizlik' },
    { label: 'NFP',                 value: macro.nfp_thousands,      suffix: 'K', desc: 'Son Tarım Dışı İst.' },
    { label: 'HY Spread',           value: macro.high_yield_spread,  suffix: 'bps', desc: 'Kredi Riski' },
  ];

  return (
    <div className="space-y-4 stagger">

      {/* Makro Özet */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MacroRegimedCard macro={macro} />
        <MacroRiskCard macro={macro} />
        <div className="card p-4 col-span-2">
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-3">
            Yield Curve
          </h3>
          <YieldCurveDisplay macro={macro} />
        </div>
      </div>

      {/* Metrik Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        {metrics.map((m) => m.value !== undefined && m.value !== null ? (
          <div key={m.label} className="metric-box card-hover cursor-default">
            <span className="metric-label">{m.label}</span>
            <span className="metric-value">
              {m.value.toFixed(m.suffix === 'K' ? 0 : 2)}{m.suffix}
            </span>
            <span className="text-[10px] text-text-muted">{m.desc}</span>
          </div>
        ) : null)}
      </div>
    </div>
  );
}

function MacroRegimedCard({ macro }: { macro: MacroSnapshot }) {
  const regimeConfig: Record<string, { color: string; emoji: string; tr: string }> = {
    GOLDILOCKS:  { color: 'text-bull', emoji: '🌟', tr: 'Altın Dönem' },
    TIGHTENING:  { color: 'text-amber-400', emoji: '🔒', tr: 'Sıkılaşma' },
    EASING:      { color: 'text-accent-cyan', emoji: '💧', tr: 'Genişleme' },
    RISK_OFF:    { color: 'text-bear', emoji: '⚠️', tr: 'Risk Kaçışı' },
    CRISIS:      { color: 'text-red-400', emoji: '🚨', tr: 'Kriz' },
    NEUTRAL:     { color: 'text-text-secondary', emoji: '⚖️', tr: 'Nötr' },
  };
  const regime = macro.macro_regime || 'NEUTRAL';
  const cfg = regimeConfig[regime] || regimeConfig.NEUTRAL;

  return (
    <div className="card p-4">
      <p className="text-[10px] text-text-muted uppercase tracking-wide mb-2">Makro Rejim</p>
      <p className="text-2xl mb-1">{cfg.emoji}</p>
      <p className={`text-sm font-bold ${cfg.color}`}>{cfg.tr}</p>
      <p className="text-[10px] text-text-muted mt-1">{regime}</p>
    </div>
  );
}

function MacroRiskCard({ macro }: { macro: MacroSnapshot }) {
  const risk = macro.macro_risk_score || 50;
  const color = risk > 70 ? '#EF4444' : risk > 50 ? '#F59E0B' : '#10B981';

  return (
    <div className="card p-4">
      <p className="text-[10px] text-text-muted uppercase tracking-wide mb-2">Makro Risk</p>
      <div className="relative w-16 h-16 mx-auto">
        <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
          <circle cx="18" cy="18" r="15" fill="none" stroke="#1E2535" strokeWidth="3" />
          <circle cx="18" cy="18" r="15" fill="none" stroke={color} strokeWidth="3"
            strokeDasharray={`${risk * 0.943} 94.3`} strokeLinecap="round" />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-xs font-mono font-bold" style={{ color }}>{risk.toFixed(0)}</span>
        </div>
      </div>
      <p className="text-[10px] text-text-muted text-center mt-1">/ 100</p>
    </div>
  );
}

function YieldCurveDisplay({ macro }: { macro: MacroSnapshot }) {
  const spread = macro.yield_curve_spread || 0;
  const isInverted = spread < 0;

  return (
    <div className="flex items-center gap-4">
      <div className="flex-1">
        <div className="flex justify-between text-xs mb-1">
          <span className="text-text-muted">2Y: {macro.us_2y_yield?.toFixed(2)}%</span>
          <span className="text-text-muted">10Y: {macro.us_10y_yield?.toFixed(2)}%</span>
        </div>
        <div className="relative h-8 flex items-end">
          <div className="w-1/3 bg-accent-blue/40 rounded-sm" style={{ height: `${(macro.us_2y_yield || 3) * 10}px` }} />
          <div className="flex-1 mx-1" />
          <div className="w-1/3 bg-accent-cyan/40 rounded-sm" style={{ height: `${(macro.us_10y_yield || 4) * 10}px` }} />
        </div>
        <p className={`text-xs mt-2 font-medium ${isInverted ? 'text-bear' : 'text-bull'}`}>
          Spread: {spread >= 0 ? '+' : ''}{spread.toFixed(2)}%
          {isInverted ? ' ⚠️ İnversiyon — Resesyon Riski' : ' ✓ Normal Eğri'}
        </p>
      </div>
    </div>
  );
}

// ----------------------------------------------------------
// TEMEL ANALİZ PANELİ
// ----------------------------------------------------------

export function FundamentalPanel({ ticker }: { ticker: string }) {
  const { data: fund, isLoading } = useFundamental(ticker);
  if (isLoading) return <PanelSkeleton rows={8} />;
  if (!fund) return <EmptyPanel message="Temel analiz verisi yüklenemedi." />;

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 stagger">

      {/* Değerleme */}
      <div className="card p-4">
        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-3">Değerleme</h3>
        <div className="space-y-2">
          <FundRow label="F/K (P/E)" value={fund.pe_ratio} suffix="x" benchmark={25} />
          <FundRow label="F/DD (P/B)" value={fund.pb_ratio} suffix="x" benchmark={3} />
          <FundRow label="F/S (P/S)" value={fund.ps_ratio} suffix="x" benchmark={5} />
          <FundRow label="PEG" value={fund.peg_ratio} suffix="x" benchmark={1.5} />
          <FundRow label="EV/EBITDA" value={fund.ev_ebitda} suffix="x" benchmark={15} />
        </div>
      </div>

      {/* Karlılık */}
      <div className="card p-4">
        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-3">Karlılık</h3>
        <div className="space-y-2">
          <FundRow label="Net Marj" value={fund.net_margin} suffix="%" multiply={100} isGoodHigh />
          <FundRow label="İşl. Marjı" value={fund.operating_margin} suffix="%" multiply={100} isGoodHigh />
          <FundRow label="Brüt Marj" value={fund.gross_margin} suffix="%" multiply={100} isGoodHigh />
          <FundRow label="ROE" value={fund.roe} suffix="%" multiply={100} isGoodHigh />
          <FundRow label="ROA" value={fund.roa} suffix="%" multiply={100} isGoodHigh />
        </div>
      </div>

      {/* EPS & Büyüme */}
      <div className="card p-4">
        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-3">EPS & Büyüme</h3>
        <div className="space-y-2">
          <FundRow label="EPS (TTM)" value={fund.eps} prefix="$" isGoodHigh />
          <FundRow label="EPS Büyüme 3Y" value={fund.eps_growth_3y} suffix="%" multiply={100} isGoodHigh />
          <FundRow label="Gelir Büyüme 3Y" value={fund.revenue_growth_3y} suffix="%" multiply={100} isGoodHigh />
          <FundRow label="Temettü" value={fund.dividend_yield} suffix="%" multiply={100} isGoodHigh />
          <FundRow label="Beta" value={fund.beta} suffix="" />
        </div>
      </div>

      {/* Temel Analiz Skoru */}
      {fund.fundamental_score !== undefined && (
        <div className="card p-4 flex flex-col items-center gap-3">
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wide self-start">
            Temel Analiz Skoru
          </h3>
          <FundamentalScoreGauge score={fund.fundamental_score} />
          <p className="text-xs text-text-secondary text-center">
            {fund.fundamental_score > 70 ? 'Güçlü Temel Değer' :
             fund.fundamental_score > 50 ? 'Orta Temel Değer' : 'Zayıf Temel Değer'}
          </p>
        </div>
      )}

      {/* Analist Öneri */}
      {fund.analyst_recommendations && fund.analyst_recommendations.length > 0 && (
        <div className="card p-4">
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-3">
            Analist Önerileri
          </h3>
          <AnalystBar rec={fund.analyst_recommendations[0]} />
        </div>
      )}

      {/* Insider & Earnings */}
      <div className="card p-4 space-y-3">
        {fund.insider_signal && (
          <div>
            <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-2">
              Insider Sinyali
            </h3>
            <div className={`badge ${fund.insider_signal === 'bullish' ? 'badge-bull' : fund.insider_signal === 'bearish' ? 'badge-bear' : 'badge-neutral'}`}>
              {fund.insider_signal === 'bullish' ? <TrendingUp size={11} /> : fund.insider_signal === 'bearish' ? <TrendingDown size={11} /> : <Minus size={11} />}
              {fund.insider_signal === 'bullish' ? 'Yoğun Alım' : fund.insider_signal === 'bearish' ? 'Yoğun Satış' : 'Nötr'}
            </div>
          </div>
        )}
        {fund.earnings_calendar?.next_earnings_date && (
          <div>
            <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-2">
              Kazanç Raporu
            </h3>
            <p className="text-xs text-text-primary font-mono">
              {new Date(fund.earnings_calendar.next_earnings_date).toLocaleDateString('tr-TR')}
            </p>
            {fund.earnings_calendar.eps_estimate && (
              <p className="text-[10px] text-text-muted">EPS Tahmin: ${fund.earnings_calendar.eps_estimate}</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ----------------------------------------------------------
// YARDIMCI BİLEŞENLER
// ----------------------------------------------------------

function CompositeSignalGauge({ value, label }: { value: number; label?: string }) {
  const pct = ((value + 1) / 2) * 100;
  const color = value > 0.2 ? '#10B981' : value < -0.2 ? '#EF4444' : '#6B7280';

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative w-28 h-28">
        <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
          <circle cx="18" cy="18" r="14" fill="none" stroke="#1E2535" strokeWidth="4" />
          <circle cx="18" cy="18" r="14" fill="none" stroke={color} strokeWidth="4"
            strokeDasharray={`${pct * 0.879} 87.96`} strokeLinecap="round"
            className="gauge-arc transition-all duration-1000" />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-mono text-lg font-bold" style={{ color }}>
            {value >= 0 ? '+' : ''}{value.toFixed(2)}
          </span>
        </div>
      </div>
      <span className={`text-sm font-semibold ${value > 0.2 ? 'text-bull' : value < -0.2 ? 'text-bear' : 'text-text-secondary'}`}>
        {label || 'Nötr'}
      </span>
    </div>
  );
}

function FundamentalScoreGauge({ score }: { score: number }) {
  const color = score > 65 ? '#10B981' : score > 45 ? '#F59E0B' : '#EF4444';
  return (
    <div className="relative w-24 h-24">
      <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
        <circle cx="18" cy="18" r="14" fill="none" stroke="#1E2535" strokeWidth="4" />
        <circle cx="18" cy="18" r="14" fill="none" stroke={color} strokeWidth="4"
          strokeDasharray={`${score * 0.8796} 87.96`} strokeLinecap="round" />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="font-mono text-base font-bold" style={{ color }}>{score.toFixed(0)}</span>
      </div>
    </div>
  );
}

function IndicatorRow({
  label, value, prefix = '', suffix = '', type, large,
}: {
  label: string; value?: number; prefix?: string; suffix?: string;
  type: 'rsi' | 'macd' | 'neutral' | 'volume'; large?: boolean;
}) {
  if (value === undefined || value === null) return null;

  const getColor = () => {
    if (type === 'rsi') return value < 30 ? 'text-bull' : value > 70 ? 'text-bear' : 'text-text-primary';
    if (type === 'macd') return value >= 0 ? 'text-bull' : 'text-bear';
    if (type === 'volume') return value > 2 ? 'text-amber-400' : value < 0.5 ? 'text-text-muted' : 'text-text-primary';
    return 'text-text-primary';
  };

  const displayValue = large ? (value / 1_000_000).toFixed(1) + 'M' : value.toFixed(2);

  return (
    <div className="flex items-center justify-between py-1 border-b border-border-subtle/50 last:border-0">
      <span className="text-xs text-text-muted">{label}</span>
      <span className={`text-xs font-mono font-semibold ${getColor()}`}>
        {prefix}{displayValue}{suffix}
      </span>
    </div>
  );
}

function FundRow({
  label, value, prefix = '', suffix = '', multiply = 1, benchmark, isGoodHigh,
}: {
  label: string; value?: number; prefix?: string; suffix?: string;
  multiply?: number; benchmark?: number; isGoodHigh?: boolean;
}) {
  if (value === undefined || value === null) return null;
  const displayVal = value * multiply;

  let color = 'text-text-primary';
  if (benchmark !== undefined) {
    color = displayVal < benchmark ? (isGoodHigh ? 'text-bear' : 'text-bull') : (isGoodHigh ? 'text-bull' : 'text-bear');
  } else if (isGoodHigh) {
    color = displayVal > 0 ? 'text-bull' : 'text-bear';
  }

  return (
    <div className="flex items-center justify-between py-1 border-b border-border-subtle/50 last:border-0">
      <span className="text-xs text-text-muted">{label}</span>
      <span className={`text-xs font-mono font-semibold ${color}`}>
        {prefix}{displayVal.toFixed(2)}{suffix}
      </span>
    </div>
  );
}

function AnalystBar({ rec }: { rec: any }) {
  const total = (rec.strong_buy + rec.buy + rec.hold + rec.sell + rec.strong_sell) || 1;
  const bullPct = ((rec.strong_buy + rec.buy) / total) * 100;
  const neutralPct = (rec.hold / total) * 100;
  const bearPct = ((rec.sell + rec.strong_sell) / total) * 100;

  return (
    <div className="space-y-2">
      <div className="flex h-3 rounded-full overflow-hidden">
        <div className="bg-bull transition-all" style={{ width: `${bullPct}%` }} />
        <div className="bg-text-muted transition-all" style={{ width: `${neutralPct}%` }} />
        <div className="bg-bear transition-all" style={{ width: `${bearPct}%` }} />
      </div>
      <div className="flex justify-between text-[10px] text-text-muted">
        <span className="text-bull">Al {rec.strong_buy + rec.buy}</span>
        <span>Tut {rec.hold}</span>
        <span className="text-bear">Sat {rec.sell + rec.strong_sell}</span>
      </div>
    </div>
  );
}

// ----------------------------------------------------------
// GENEL YARDIMCI BİLEŞENLER
// ----------------------------------------------------------

function PanelSkeleton({ rows }: { rows: number }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="card p-4 space-y-3">
          <div className="skeleton h-4 w-28" />
          {Array.from({ length: rows }).map((_, j) => (
            <div key={j} className="skeleton h-3 w-full" />
          ))}
        </div>
      ))}
    </div>
  );
}

function EmptyPanel({ message }: { message: string }) {
  return (
    <div className="card p-8 flex items-center justify-center">
      <p className="text-sm text-text-muted">{message}</p>
    </div>
  );
}

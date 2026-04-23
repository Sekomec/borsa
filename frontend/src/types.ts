export type Timeframe = '1d' | '1w' | '1mo' | '3mo' | '1y' | '1h' | '5m';

export type Direction = 'up' | 'down' | 'sideways';

export interface OHLCVBar {
  timestamp: string;
  open_price: number;
  high_price: number;
  low_price: number;
  close_price: number;
  volume?: number;
  vwap?: number | null;
}

export interface MacroSnapshot {
  fed_rate?: number | null;
  us_10y_yield?: number | null;
  us_2y_yield?: number | null;
  yield_curve_spread?: number | null;
  vix?: number | null;
  dxy?: number | null;
  cpi_yoy_pct?: number | null;
  unemployment_rate?: number | null;
  nfp_thousands?: number | null;
  high_yield_spread?: number | null;
  macro_risk_score?: number | null;
  macro_regime?: string | null;
}

export interface StockInfo {
  ticker: string;
  company_name?: string;
  exchange?: string;
  sector?: string;
  industry?: string;
  market_cap?: number;
}

export interface SentimentResponse {
  ticker: string;
  overall_score: number;
  sentiment_label: string;
  reddit_score?: number | null;
  stocktwits_score?: number | null;
  news_score?: number | null;
  total_mentions?: number;
  news_article_count?: number;
  top_headlines?: Array<{ title: string; source: string; published_at: string; url: string }>;
  last_updated?: string;
}

export interface FundamentalResponse {
  ticker?: string;
  pe_ratio?: number;
  pb_ratio?: number;
  ps_ratio?: number;
  peg_ratio?: number;
  ev_ebitda?: number;
  eps?: number;
  eps_growth_3y?: number;
  revenue_growth_3y?: number;
  gross_margin?: number;
  operating_margin?: number;
  net_margin?: number;
  roe?: number;
  roa?: number;
  dividend_yield?: number;
  debt_to_equity?: number;
  beta?: number;
  fundamental_score?: number;
  insider_signal?: 'bullish' | 'bearish' | 'neutral';
  analyst_recommendations?: any[];
  earnings_calendar?: any;
}

export interface TechnicalAnalysisResponse {
  indicators: Record<string, any>;
  signals: Record<string, any>;
  patterns: string[];
}

export interface PredictionRequest {
  ticker: string;
  timeframe: Timeframe;
  include_technical?: boolean;
  include_sentiment?: boolean;
  include_fundamental?: boolean;
  include_macro?: boolean;
}

export interface PredictionResponse {
  ticker: string;
  company_name?: string;
  current_price: number;
  timeframe: Timeframe;
  predicted_price: number;
  lower_bound?: number | null;
  upper_bound?: number | null;
  predicted_return_pct?: number | null;
  direction: Direction;
  direction_confidence: number;
  technical_score?: number | null;
  sentiment_score?: number | null;
  fundamental_score?: number | null;
  macro_score?: number | null;
  risk_level: string;
  volatility_estimate?: number | null;
  anomaly_detected?: boolean;
  anomaly_description?: string | null;
  model_version: string;
  ensemble_weights?: Record<string, number> | null;
  model_contributions?: Record<string, number> | null;
  explanation?: string | null;
  disclaimer: string;
}


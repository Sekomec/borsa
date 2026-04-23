/**
 * PATCH for frontend/src/lib/api.ts
 *
 * 1. Add EventContext interface
 * 2. Add event_context field to PredictionResponse type
 * 3. Add include_events to PredictionRequest type
 */

// ── ADD these types (merge into your existing types file) ─────────────────

export interface EventContext {
  next_earnings_date?: string | null;
  days_to_next_earnings?: number | null;
  earnings_window?: boolean;
  next_fomc_date?: string | null;
  days_to_next_fomc?: number | null;
  fomc_window?: boolean;
  next_cpi_date?: string | null;
  days_to_next_cpi?: number | null;
  cpi_window?: boolean;
  combined_vol_multiplier?: number;
}

// ── ADD include_events to your existing PredictionRequest interface ────────
//
//   export interface PredictionRequest {
//     ticker: string;
//     timeframe: "1d" | "1w" | "1mo" | "3mo" | "1y";
//     include_technical?: boolean;
//     include_sentiment?: boolean;
//     include_fundamental?: boolean;
//     include_macro?: boolean;
//     include_events?: boolean;          // ← ADD THIS
//   }

// ── ADD event_context to your existing PredictionResponse interface ────────
//
//   export interface PredictionResponse {
//     ticker: string;
//     ...existing fields...
//     event_context?: EventContext | null;  // ← ADD THIS
//   }

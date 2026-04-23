/**
 * EventBadge.tsx
 * Place in: frontend/src/components/dashboard/EventBadge.tsx
 *
 * Usage inside PredictionPanel.tsx:
 *   import EventBadge from "@/components/dashboard/EventBadge";
 *   <EventBadge eventContext={prediction.event_context} />
 */

import React from "react";

interface EventContext {
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

interface Props {
  eventContext?: EventContext | null;
}

function Badge({
  label,
  days,
  urgent,
}: {
  label: string;
  days: number | null | undefined;
  urgent: boolean;
}) {
  if (days == null) return null;

  const bg = urgent
    ? "bg-amber-100 text-amber-800 border-amber-300"
    : "bg-slate-100 text-slate-600 border-slate-200";

  const daysText = days === 0 ? "bugün" : days === 1 ? "yarın" : `${days} gün sonra`;

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium ${bg}`}
    >
      {urgent && (
        <svg
          className="h-3 w-3"
          viewBox="0 0 20 20"
          fill="currentColor"
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z"
            clipRule="evenodd"
          />
        </svg>
      )}
      {label}: {daysText}
    </span>
  );
}

export default function EventBadge({ eventContext }: Props) {
  // Render nothing if no context — never breaks the parent panel
  if (!eventContext) return null;

  const hasAnyEvent =
    eventContext.days_to_next_earnings != null ||
    eventContext.days_to_next_fomc != null ||
    eventContext.days_to_next_cpi != null;

  if (!hasAnyEvent) return null;

  const volAdjusted =
    eventContext.combined_vol_multiplier != null &&
    eventContext.combined_vol_multiplier > 1.0;

  return (
    <div className="mt-3 flex flex-wrap gap-2">
      <Badge
        label="Earnings"
        days={eventContext.days_to_next_earnings}
        urgent={!!eventContext.earnings_window}
      />
      <Badge
        label="FOMC"
        days={eventContext.days_to_next_fomc}
        urgent={!!eventContext.fomc_window}
      />
      <Badge
        label="CPI"
        days={eventContext.days_to_next_cpi}
        urgent={!!eventContext.cpi_window}
      />

      {volAdjusted && (
        <span className="inline-flex items-center gap-1 rounded-full border border-orange-200 bg-orange-50 px-2.5 py-0.5 text-xs font-medium text-orange-700">
          ⚡ Vol ×{eventContext.combined_vol_multiplier?.toFixed(2)} uygulandı
        </span>
      )}
    </div>
  );
}

type EventContext = {
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
} | null | undefined;

export default function EventBadge({ eventContext }: { eventContext: EventContext }) {
  if (!eventContext) return null;

  const chips: Array<{ label: string; tone: 'neutral' | 'warn' }> = [];

  if (eventContext.days_to_next_earnings !== null && eventContext.days_to_next_earnings !== undefined) {
    chips.push({
      label: `Earnings: ${eventContext.days_to_next_earnings}g`,
      tone: eventContext.earnings_window ? 'warn' : 'neutral',
    });
  }
  if (eventContext.days_to_next_fomc !== null && eventContext.days_to_next_fomc !== undefined) {
    chips.push({
      label: `FOMC: ${eventContext.days_to_next_fomc}g`,
      tone: eventContext.fomc_window ? 'warn' : 'neutral',
    });
  }
  if (eventContext.days_to_next_cpi !== null && eventContext.days_to_next_cpi !== undefined) {
    chips.push({
      label: `CPI: ${eventContext.days_to_next_cpi}g`,
      tone: eventContext.cpi_window ? 'warn' : 'neutral',
    });
  }

  if (!chips.length) return null;

  return (
    <div className="flex flex-wrap gap-2 mt-3">
      {chips.map((c) => (
        <span
          key={c.label}
          className={`badge text-[10px] ${
            c.tone === 'warn' ? 'badge-neutral border border-amber-400/30 text-amber-400 bg-amber-400/10' : 'badge-neutral'
          }`}
          title="Yaklaşan olaylar"
        >
          {c.label}
        </span>
      ))}
      {typeof eventContext.combined_vol_multiplier === 'number' && eventContext.combined_vol_multiplier > 1 ? (
        <span className="badge badge-neutral text-[10px]" title="Olay bazlı belirsizlik çarpanı">
          Vol×{eventContext.combined_vol_multiplier.toFixed(2)}
        </span>
      ) : null}
    </div>
  );
}


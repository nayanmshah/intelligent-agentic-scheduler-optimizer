import { ContributionBar } from "./ContributionBar";
import type { Offer } from "@/lib/api";

/**
 * FR-053: seven elements, every one present. FR-052: exactly one primary action.
 *
 * The reason line is the thing an operator reads aloud, so it sits directly under
 * the facts and above the button -- nothing competes with it for attention.
 */
export function OfferCard({
  offer,
  index,
  onHold,
  booked,
}: {
  offer: Offer;
  index: number;
  onHold: (o: Offer) => void;
  booked: boolean;
}) {
  return (
    <article
      className="flex flex-col gap-2 rounded border p-3 transition-transform"
      style={{
        borderColor: offer.is_overflow ? "var(--warn)" : "var(--line)",
        background: "var(--surface)",
        boxShadow: "0 1px 2px rgba(16,24,40,0.06)",
      }}
    >
      {offer.is_overflow && (
        <span className="text-[0.65rem] font-semibold uppercase tracking-wide"
              style={{ color: "var(--warn)" }}>
          Not what you asked for
        </span>
      )}
      {offer.emergency_hold_released && (
        <span className="text-[0.65rem] font-semibold uppercase tracking-wide"
              style={{ color: "var(--warn)" }}>
          Emergency hold released
        </span>
      )}

      <header>
        <div className="text-sm font-semibold">
          {offer.weekday} {offer.date_display}
        </div>
        <div className="text-lg font-semibold">{offer.start_display}</div>
        <div className="text-xs" style={{ color: "var(--ink-soft)" }}>
          {offer.provider_name} · {offer.type_name} · {offer.duration_min} min
        </div>
      </header>

      <ContributionBar contributions={offer.contributions} score={offer.score} />

      {/* Read aloud verbatim. Lint-enforced: one sentence, <=25 words, no jargon. */}
      <p className="text-sm leading-snug">{offer.reason}</p>

      <button
        onClick={() => onHold(offer)}
        disabled={booked}
        className="mt-auto rounded px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        style={{ background: "var(--accent)" }}
      >
        {booked ? "Booked" : `Hold  ${index}`}
      </button>
    </article>
  );
}

import { ContributionBar } from "./ContributionBar";
import type { Offer } from "@/lib/api";

/**
 * FR-053: seven elements, every one present. FR-052: exactly one primary action.
 *
 * The card reads top-to-bottom in the order an operator speaks: the when (big),
 * the who, the evidence, then the sentence they read aloud — set in serif, because
 * it is the one piece of *prose* on the screen and deserves to look like it.
 * An offer that misses the request wears its banner at the very top, before the
 * time, so it cannot be skimmed past (FR-038).
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
      className="card rise flex flex-col overflow-hidden"
      style={{
        animationDelay: `${index * 70}ms`,
        borderColor: offer.is_overflow ? "var(--warn-line)" : "var(--line)",
      }}
    >
      {(offer.is_overflow || offer.emergency_hold_released) && (
        <div
          className="px-4 py-1.5 text-[0.66rem] font-bold uppercase tracking-[0.08em]"
          style={{ background: "var(--warn-bg)", color: "var(--warn)" }}
        >
          {offer.is_overflow ? "Not what you asked for" : "Emergency hold released"}
        </div>
      )}

      <div className="flex flex-1 flex-col gap-3 p-4">
        <header className="flex items-start justify-between gap-2">
          <div>
            <div className="text-[0.82rem] font-semibold" style={{ color: "var(--ink-soft)" }}>
              {offer.weekday} {offer.date_display}
            </div>
            <div className="text-[1.9rem] font-bold leading-tight tracking-tight">
              {offer.start_display}
            </div>
            <div className="mt-0.5 text-xs" style={{ color: "var(--ink-soft)" }}>
              <span className="font-medium" style={{ color: "var(--ink)" }}>
                {offer.provider_name}
              </span>
              {" · "}
              {offer.type_name} · {offer.duration_min} min
            </div>
          </div>
          {/* Rank + the keyboard shortcut that holds it (NFR-25). */}
          <span
            aria-hidden
            className="kbd mt-1 !text-[0.8rem]"
            title={`Press ${index} to hold`}
          >
            {index}
          </span>
        </header>

        <ContributionBar contributions={offer.contributions} score={offer.score} />

        {/* Read aloud verbatim. Lint-enforced: one sentence, <=25 words, no jargon. */}
        <p
          className="read-aloud border-l-2 pl-3"
          style={{ borderColor: offer.is_overflow ? "var(--warn-line)" : "var(--accent-soft)" }}
        >
          {offer.reason}
        </p>

        <button
          onClick={() => onHold(offer)}
          disabled={booked}
          className={booked ? "mt-auto rounded-lg px-3 py-2 text-sm font-semibold" : "btn-primary mt-auto px-3 py-2 text-sm"}
          style={
            booked
              ? { background: "var(--ok-bg)", color: "var(--ok)", border: "1px solid var(--ok-line)" }
              : undefined
          }
        >
          {booked ? "✓ Booked" : `Hold ${index}`}
        </button>
      </div>
    </article>
  );
}

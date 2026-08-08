import { AXIS_LABELS, AXIS_STYLE, type Contribution } from "@/lib/api";

/**
 * FR-080 / FR-047. The score is **always decomposed, never a naked number**, and the
 * segments must sum to the total that is displayed.
 *
 * NFR-24: segments carry labels and a fixed order, so a greyscale screenshot stays
 * interpretable. Colour is reinforcement, never the only signal.
 */
export function ContributionBar({
  contributions,
  score,
}: {
  contributions: Contribution[];
  score: number;
}) {
  const total = contributions.reduce((sum, c) => sum + c.weighted, 0) || 1;
  return (
    <div>
      <div
        className="flex h-3 w-full overflow-hidden rounded-sm"
        role="img"
        aria-label={contributions
          .map((c) => `${AXIS_LABELS[c.axis]} ${Math.round((c.weighted / total) * 100)}%`)
          .join(", ")}
      >
        {contributions.map((c) => (
          <div
            key={c.axis}
            title={`${AXIS_LABELS[c.axis]}: ${c.value.toFixed(2)} × ${c.weight.toFixed(2)} = ${c.weighted.toFixed(3)}`}
            style={{
              width: `${(c.weighted / total) * 100}%`,
              background: AXIS_STYLE[c.axis]?.fill ?? "#ccc",
            }}
          />
        ))}
      </div>
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[0.65rem]"
           style={{ color: "var(--ink-soft)" }}>
        {contributions.map((c) => (
          <span key={c.axis} className="inline-flex items-center gap-1">
            <span
              className="inline-block h-2 w-2 rounded-[1px]"
              style={{ background: AXIS_STYLE[c.axis]?.fill ?? "#ccc" }}
            />
            {AXIS_LABELS[c.axis]} {c.weighted.toFixed(2)}
          </span>
        ))}
        <span className="ml-auto font-semibold" style={{ color: "var(--ink)" }}>
          = {(score * 100).toFixed(0)}%
        </span>
      </div>
    </div>
  );
}

/**
 * FR-081. Stated **in words with a number**, not as a bare figure.
 *
 * This is the key result on the policy panel: it converts "the weights are
 * arbitrary" from an objection into a measurement. The recommendation is robust to
 * the weights, or it is not, and the number says which — a much stronger claim than
 * any particular weight being correct.
 */
export function StabilityIndicator({
  sentence,
  pct,
  samples,
}: {
  sentence: string;
  pct: number;
  samples: number;
}) {
  const solid = pct >= 70;
  const tone = solid ? "var(--accent)" : "var(--warn)";
  return (
    <section className="card p-4">
      <div className="flex items-baseline gap-3">
        <span
          className="text-[2rem] font-bold leading-none tabular-nums tracking-tight"
          style={{ color: tone }}
        >
          {pct}%
        </span>
        <span className="text-sm" style={{ color: "var(--ink-soft)" }}>
          {sentence}
        </span>
      </div>
      <div
        className="mt-2.5 h-1.5 w-full overflow-hidden rounded-full"
        style={{ background: "var(--page)" }}
      >
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{ width: `${pct}%`, background: tone }}
        />
      </div>
      <p className="mt-1.5 text-[0.66rem]" style={{ color: "var(--ink-faint)" }}>
        {samples} seeded weight vectors · reproducible run to run
      </p>
    </section>
  );
}

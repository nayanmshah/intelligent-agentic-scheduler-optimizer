/**
 * FR-081. Stated **in words with a number**, not as a bare figure.
 *
 * This is the key result on the policy panel: it converts "the weights are
 * arbitrary" from an objection into a measurement. The recommendation is robust to
 * the weights, or it is not, and the number says which -- a much stronger claim than
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
  const tone = pct >= 70 ? "var(--accent)" : "var(--warn)";
  return (
    <section
      className="rounded border p-3"
      style={{ borderColor: "var(--line)", background: "var(--surface)" }}
    >
      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-semibold tabular-nums" style={{ color: tone }}>
          {pct}%
        </span>
        <span className="text-sm">{sentence}</span>
      </div>
      <div className="mt-1 h-1.5 w-full rounded" style={{ background: "var(--page)" }}>
        <div className="h-full rounded" style={{ width: `${pct}%`, background: tone }} />
      </div>
      <p className="mt-1 text-[0.65rem]" style={{ color: "var(--ink-soft)" }}>
        {samples} seeded weight vectors · reproducible run to run
      </p>
    </section>
  );
}

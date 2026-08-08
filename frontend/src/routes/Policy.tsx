import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, AXIS_LABELS } from "@/lib/api";
import { StabilityIndicator } from "@/components/StabilityIndicator";

const AXES = ["time_fit", "continuity", "efficiency", "prime_time"] as const;

/**
 * Practice policy. A **separate surface**, deliberately not reachable from the
 * operator flow (FR-076): putting weights in front of the front desk invites
 * per-call adjustment, which destroys the decision consistency the product sells.
 *
 * NFR-19 states plainly that this separation is a UX boundary, **not** a security
 * one. Any deployment beyond a single trusted workstation must add real
 * authorization before this panel is exposed.
 */
export default function Policy() {
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: api.profiles });
  const traces = useQuery({ queryKey: ["traces"], queryFn: api.traces });
  const [weights, setWeights] = useState<Record<string, number>>({
    time_fit: 0.35, continuity: 0.25, efficiency: 0.25, prime_time: 0.15,
  });
  const [ranked, setRanked] = useState<{ provider_name: string | null; start_display: string | null; score: number }[]>([]);
  const [elapsed, setElapsed] = useState<number | null>(null);
  const [stability, setStability] = useState<{ sentence: string; held_pct: number; samples: number } | null>(null);

  const requestId = traces.data?.decisions[0]?.id ?? null;

  /** Sliders renormalise so the vector always sums to 1.0 (FR-078). */
  const setAxis = (axis: string, value: number) => {
    const others = AXES.filter((a) => a !== axis);
    const remaining = Math.max(0, 1 - value);
    const otherSum = others.reduce((s, a) => s + (weights[a] ?? 0), 0) || 1;
    const next: Record<string, number> = { [axis]: value };
    others.forEach((a) => {
      next[a] = ((weights[a] ?? 0) / otherSum) * remaining;
    });
    setWeights(next);
  };

  useEffect(() => {
    if (!requestId) return;
    const t0 = performance.now();
    api.rerank(requestId, weights).then((r) => {
      setElapsed(performance.now() - t0);
      setRanked(r.ranked);
    });
    api.stability(requestId).then(setStability);
  }, [requestId, weights]);

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-4 p-5">
      <h1 className="text-lg font-semibold">Practice scheduling policy</h1>
      <p className="text-xs" style={{ color: "var(--ink-soft)" }}>
        These weights are a <em>profile, not a universal truth</em>. Different practices
        genuinely want different things.
      </p>

      <section className="flex flex-wrap gap-2">
        {profiles.data?.profiles.map((p) => (
          <button
            key={p.id}
            onClick={() => {
              api.setProfile(p.id).then(() => profiles.refetch());
              setWeights(p.weights);
            }}
            className="rounded border px-3 py-1 text-sm"
            style={{
              borderColor: profiles.data?.active === p.id ? "var(--accent)" : "var(--line)",
              background: "var(--surface)",
            }}
          >
            {p.name}
            {p.is_fitted && <span className="ml-1 text-[0.65rem]">· fitted</span>}
          </button>
        ))}
      </section>

      <section className="flex flex-col gap-3 rounded border p-3"
               style={{ borderColor: "var(--line)", background: "var(--surface)" }}>
        {AXES.map((axis) => (
          <label key={axis} className="flex items-center gap-3 text-sm">
            <span className="w-36">{AXIS_LABELS[axis]}</span>
            <input
              type="range" min={0} max={1} step={0.01}
              value={weights[axis] ?? 0}
              onChange={(e) => setAxis(axis, Number(e.target.value))}
              className="flex-1"
            />
            <span className="w-12 text-right tabular-nums">
              {(weights[axis] ?? 0).toFixed(2)}
            </span>
          </label>
        ))}
        <p className="text-[0.65rem]" style={{ color: "var(--ink-soft)" }}>
          Sum {Object.values(weights).reduce((a, b) => a + b, 0).toFixed(2)}
          {elapsed !== null && ` · re-ranked in ${elapsed.toFixed(0)}ms with zero model calls`}
        </p>
      </section>

      {stability && (
        <StabilityIndicator
          sentence={stability.sentence}
          pct={stability.held_pct}
          samples={stability.samples}
        />
      )}

      {ranked.length > 0 && (
        <section className="rounded border p-3"
                 style={{ borderColor: "var(--line)", background: "var(--surface)" }}>
          <h2 className="mb-2 text-sm font-semibold">Top 3 under these weights</h2>
          <ol className="text-sm">
            {ranked.map((r, i) => (
              <li key={i} className="flex gap-3 py-0.5">
                <span className="w-10 tabular-nums">{(r.score * 100).toFixed(0)}%</span>
                <span>{r.provider_name ?? "—"} {r.start_display ?? ""}</span>
              </li>
            ))}
          </ol>
        </section>
      )}
    </main>
  );
}

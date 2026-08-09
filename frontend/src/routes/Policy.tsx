import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, AXIS_LABELS, AXIS_STYLE } from "@/lib/api";
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
  // Start from the ACTIVE profile once it loads. A hardcoded default here showed
  // sliders that disagreed with the policy actually ranking requests — and a 0%
  // stability figure computed against a top-3 the shipped profile never produced.
  const [weights, setWeightsRaw] = useState<Record<string, number> | null>(null);
  const active = profiles.data?.profiles.find((p) => p.id === profiles.data?.active);
  const effective = weights ?? active?.weights ?? {
    time_fit: 0.35, continuity: 0.25, efficiency: 0.25, prime_time: 0.15,
  };
  const setWeights = setWeightsRaw;
  const [ranked, setRanked] = useState<
    {
      provider_name: string | null;
      start_display: string | null;
      room_name?: string;
      score: number;
      was_offered: boolean;
    }[]
  >([]);
  const [elapsed, setElapsed] = useState<number | null>(null);
  const [stability, setStability] = useState<{ sentence: string; held_pct: number; samples: number } | null>(null);

  const requestId = traces.data?.decisions[0]?.id ?? null;

  /** Sliders renormalise so the vector always sums to 1.0 (FR-078). */
  const setAxis = (axis: string, value: number) => {
    const others = AXES.filter((a) => a !== axis);
    const remaining = Math.max(0, 1 - value);
    const otherSum = others.reduce((s, a) => s + (effective[a] ?? 0), 0) || 1;
    const next: Record<string, number> = { [axis]: value };
    others.forEach((a) => {
      next[a] = ((effective[a] ?? 0) / otherSum) * remaining;
    });
    setWeights(next);
  };

  useEffect(() => {
    if (!requestId) return;
    const t0 = performance.now();
    api.rerank(requestId, effective).then((r) => {
      setElapsed(performance.now() - t0);
      setRanked(r.ranked);
    });
    // Recomputed against the weights on screen, so the figure and the list below it
    // are always talking about the same three slots.
    api.stability(requestId, effective).then(setStability);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestId, JSON.stringify(effective)]);

  return (
    <main className="mx-auto flex max-w-[880px] flex-col gap-5 px-6 py-7">
      <header>
        <h1 className="text-[1.35rem] font-bold tracking-tight">Practice scheduling policy</h1>
        <p className="mt-1 text-sm" style={{ color: "var(--ink-soft)" }}>
          These weights are a <em>profile, not a universal truth</em> — different practices
          genuinely want different things. Set once, applied to every request.
        </p>
      </header>

      <section className="flex flex-wrap gap-2">
        {profiles.data?.profiles.map((p) => {
          const active = profiles.data?.active === p.id;
          return (
            <button
              key={p.id}
              onClick={() => {
                api.setProfile(p.id).then(() => profiles.refetch());
                setWeights(p.weights);
              }}
              className={active ? "btn-primary px-4 py-1.5 text-sm" : "btn-quiet px-4 py-1.5 text-sm"}
            >
              {p.name}
              {p.is_fitted && (
                <span className="text-[0.62rem] opacity-75">· fitted, not applied</span>
              )}
            </button>
          );
        })}
      </section>

      <section className="card flex flex-col gap-4 p-5">
        {AXES.map((axis) => (
          <label key={axis} className="flex items-center gap-4 text-sm">
            <span className="flex w-40 items-center gap-2">
              <span
                aria-hidden
                className="inline-block h-2.5 w-2.5 rounded-[3px]"
                style={{ background: AXIS_STYLE[axis]?.fill }}
              />
              <span className="font-medium">{AXIS_LABELS[axis]}</span>
            </span>
            <input
              type="range" min={0} max={1} step={0.01}
              value={effective[axis] ?? 0}
              onChange={(e) => setAxis(axis, Number(e.target.value))}
              className="h-1.5 flex-1 cursor-pointer"
            />
            <span className="w-12 text-right font-semibold tabular-nums">
              {(effective[axis] ?? 0).toFixed(2)}
            </span>
          </label>
        ))}
        <p
          className="border-t pt-3 text-[0.68rem]"
          style={{ borderColor: "var(--line)", color: "var(--ink-faint)" }}
        >
          Sum {Object.values(effective).reduce((a, b) => a + b, 0).toFixed(2)}
          {elapsed !== null && (
            <>
              {" · re-ranked in "}
              <strong style={{ color: "var(--accent)" }}>{elapsed.toFixed(0)}ms</strong>
              {" with zero model calls"}
            </>
          )}
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
        <section className="card p-5">
          <h2 className="label-caps mb-3">Top 3 under these weights</h2>
          <ol className="flex flex-col">
            {ranked.map((r, i) => (
              <li
                key={i}
                className="flex items-baseline gap-4 border-t py-2 text-sm first:border-t-0"
                style={{ borderColor: "var(--line)" }}
              >
                <span className="w-8 text-[0.8rem] font-bold tabular-nums" style={{ color: "var(--ink-faint)" }}>
                  {i + 1}
                </span>
                <span className="w-14 font-bold tabular-nums" style={{ color: "var(--accent)" }}>
                  {(r.score * 100).toFixed(0)}%
                </span>
                <span className="font-medium">
                  {r.provider_name ?? "—"} {r.start_display ?? ""}
                  {/* Two rooms can hold the same hygienist at the same minute when the
                      tier has nothing else left; without the room these read as one row
                      printed twice. Shown only when it is actually ambiguous. */}
                  {r.room_name &&
                    ranked.filter(
                      (o) =>
                        o.provider_name === r.provider_name &&
                        o.start_display === r.start_display,
                    ).length > 1 && (
                      <span className="ml-1.5 text-xs" style={{ color: "var(--ink-faint)" }}>
                        {r.room_name}
                      </span>
                    )}
                </span>
                {/* Naming what the weighting *changed* is the point of this screen:
                    a row that was not in the original three is the evidence. */}
                {!r.was_offered && (
                  <span
                    className="rounded-full px-2 py-0.5 text-[0.62rem] font-semibold"
                    style={{ background: "var(--ok-bg)", color: "var(--ok)" }}
                  >
                    newly promoted
                  </span>
                )}
              </li>
            ))}
          </ol>
        </section>
      )}
    </main>
  );
}

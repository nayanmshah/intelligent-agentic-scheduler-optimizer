import type { StageEvent } from "@/lib/api";

/**
 * What the pipeline is doing, while it does it — as a horizontal stepper.
 *
 * A live request is a few seconds of sequential model calls. A button that only says
 * "…" for that long reads as frozen — the first person to use it reported exactly
 * that. So the wait *shows the pipeline working*: all four stages appear the moment
 * the request starts, the running one pulses, and each fills in with its measured
 * duration as it closes.
 *
 * The durations are measured, not animated. A stage that takes 2.5 seconds shows
 * 2.5 seconds, and the implementation that answered is named beside it — so a silent
 * fallback is visible here, not only in the trace panel (NFR-16).
 */
export function StageProgress({ stages }: { stages: StageEvent[] }) {
  if (stages.length === 0) return null;

  const firstPending = stages.findIndex((s) => !s.done);

  return (
    <section
      className="card rise flex items-stretch overflow-hidden"
      aria-live="polite"
      aria-busy={firstPending !== -1}
    >
      {stages.map((s, i) => {
        const running = !s.done && i === firstPending;
        return (
          <div
            key={s.stage}
            className="relative flex flex-1 flex-col gap-1 px-4 py-3"
            style={{
              borderLeft: i > 0 ? "1px solid var(--line)" : "none",
              background: running ? "var(--accent-faint)" : "transparent",
              transition: "background 200ms ease",
            }}
          >
            {/* progress underline: done = full accent, running = pulsing */}
            <span
              aria-hidden
              className={running ? "breathe absolute inset-x-0 top-0 h-0.5" : "absolute inset-x-0 top-0 h-0.5"}
              style={{
                background: s.done || running ? "var(--accent)" : "var(--line)",
                opacity: s.done ? 1 : running ? undefined : 0.6,
              }}
            />
            <span className="flex items-center gap-1.5">
              <span
                aria-hidden
                className="text-[0.72rem]"
                style={{ color: s.done ? "var(--accent)" : "var(--ink-faint)" }}
              >
                {s.done ? "✓" : running ? "▸" : "·"}
              </span>
              <span
                className="text-[0.8rem]"
                style={{
                  color: s.done || running ? "var(--ink)" : "var(--ink-faint)",
                  fontWeight: running ? 600 : 500,
                }}
              >
                {s.label}
                {running && "…"}
              </span>
            </span>
            {s.done && (
              <span
                className="pl-4 text-[0.68rem] tabular-nums"
                style={{ color: "var(--ink-soft)", fontFamily: "var(--mono)" }}
              >
                {formatMs(s.ms ?? 0)}
                {/* Which implementation answered, so a silent fallback is visible
                    here and not only in the trace panel (NFR-16). */}
                {s.implementation && s.implementation !== "template" && ` · ${s.implementation}`}
                {s.fallback_fired && " · fell back"}
              </span>
            )}
          </div>
        );
      })}
    </section>
  );
}

function formatMs(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
}

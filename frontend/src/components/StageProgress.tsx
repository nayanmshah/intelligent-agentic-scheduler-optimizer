import type { StageEvent } from "@/lib/api";

/**
 * What the pipeline is doing, while it does it.
 *
 * A live request is three sequential model calls and takes ~15 seconds. The console
 * used to show a "…" on the button for that whole time, which the first person to
 * use it reported as "stuck" — and they were right to: nothing on screen said
 * otherwise.
 *
 * So this is the honest fix for a latency complaint *and* the clearest demonstration
 * that there are agents here at all. Each row appears greyed the moment the request
 * starts and fills in with its real duration as that stage closes, so the wait reads
 * as progress rather than as a hang.
 *
 * The durations are measured, not animated. A stage that takes 10 seconds shows
 * 10 seconds.
 */
export function StageProgress({ stages }: { stages: StageEvent[] }) {
  if (stages.length === 0) return null;

  const firstPending = stages.findIndex((s) => !s.done);

  return (
    <section
      className="flex flex-col gap-1 rounded border p-3 text-sm"
      style={{ borderColor: "var(--line)", background: "var(--surface)" }}
      aria-live="polite"
      aria-busy={firstPending !== -1}
    >
      {stages.map((s, i) => {
        const running = !s.done && i === firstPending;
        return (
          <div key={s.stage} className="flex items-baseline gap-2">
            <span
              aria-hidden
              className="w-4 text-center"
              style={{ color: s.done ? "var(--accent)" : "var(--ink-soft)" }}
            >
              {s.done ? "✓" : running ? "▸" : "·"}
            </span>
            <span
              style={{
                color: s.done || running ? "var(--ink)" : "var(--ink-soft)",
                fontWeight: running ? 600 : 400,
              }}
            >
              {s.label}
              {running && "…"}
            </span>
            {s.done && (
              <span className="tabular-nums text-xs" style={{ color: "var(--ink-soft)" }}>
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

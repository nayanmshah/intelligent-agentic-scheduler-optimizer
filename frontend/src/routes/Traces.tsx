import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

/**
 * Trace and replay. Reads the in-process store only (FR-087) — with the container
 * runtime stopped, this panel renders and replays normally.
 *
 * Degradation is silent to the operator and **loud here**: every fallback and gate
 * firing that the console deliberately hid shows up in this list.
 */
export default function Traces() {
  const traces = useQuery({ queryKey: ["traces"], queryFn: api.traces, refetchInterval: 2000 });
  const [selected, setSelected] = useState<string | null>(null);
  const [replay, setReplay] = useState<{ identical: boolean } | null>(null);

  const spans = useQuery({
    queryKey: ["trace", selected],
    queryFn: () => api.trace(selected!),
    enabled: !!selected,
  });

  const maxMs = Math.max(1, ...(spans.data?.spans.map((s) => Number(s.duration_ms)) ?? [1]));

  return (
    <main className="mx-auto grid max-w-[1120px] grid-cols-[1fr_1.4fr] gap-5 px-6 py-7">
      <section>
        <h1 className="label-caps mb-3">Decisions</h1>
        <ul className="flex flex-col gap-2">
          {traces.data?.decisions.map((d) => {
            const active = selected === d.trace_id;
            return (
              <li key={d.id}>
                <button
                  onClick={() => {
                    setSelected(d.trace_id);
                    setReplay(null);
                  }}
                  className="card w-full px-3.5 py-2.5 text-left text-xs transition-all"
                  style={{
                    borderColor: active ? "var(--accent)" : "var(--line)",
                    boxShadow: active ? "0 0 0 1px var(--accent)" : undefined,
                  }}
                >
                  <div className="truncate font-medium" style={{ fontFamily: "var(--serif)" }}>
                    “{d.raw_text}”
                  </div>
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    <span
                      className="rounded-full px-1.5 py-0.5 text-[0.62rem] font-semibold"
                      style={{ background: "var(--accent-soft)", color: "var(--accent-deep)" }}
                    >
                      {d.offers} offers
                    </span>
                    {d.question && (
                      <span
                        className="rounded-full px-1.5 py-0.5 text-[0.62rem] font-semibold"
                        style={{ background: "var(--accent-faint)", color: "var(--accent-deep)" }}
                      >
                        asked a question
                      </span>
                    )}
                    {d.fallback_fired.length > 0 && (
                      <span
                        className="rounded-full px-1.5 py-0.5 text-[0.62rem] font-semibold"
                        style={{ background: "var(--warn-bg)", color: "var(--warn)" }}
                      >
                        fallback: {d.fallback_fired.join(",")}
                      </span>
                    )}
                  </div>
                </button>
                {active && (
                  <button
                    onClick={() => api.replay(d.id).then(setReplay)}
                    className="btn-quiet mt-1.5 px-2.5 py-1 text-[0.68rem]"
                  >
                    Replay and check byte equality
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      </section>

      <section>
        <h2 className="label-caps mb-3">Spans</h2>
        {replay && (
          <p
            className="mb-3 rounded-xl border px-3.5 py-2.5 text-xs font-medium"
            style={
              replay.identical
                ? { borderColor: "var(--ok-line)", background: "var(--ok-bg)", color: "var(--ok)" }
                : { borderColor: "var(--warn-line)", background: "var(--warn-bg)", color: "var(--warn)" }
            }
          >
            {replay.identical
              ? "✓ Replay reproduced the decision byte for byte."
              : "Replay differed — see the field-level diff in the response."}
          </p>
        )}
        {spans.data && (
          <div className="card overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left" style={{ background: "var(--page)" }}>
                  <th className="label-caps px-3.5 py-2 !font-semibold">stage</th>
                  <th className="label-caps py-2 !font-semibold">duration</th>
                  <th className="label-caps py-2 !font-semibold">detail</th>
                </tr>
              </thead>
              <tbody>
                {spans.data.spans.map((s, i) => (
                  <tr key={i} className="border-t align-top" style={{ borderColor: "var(--line)" }}>
                    <td className="px-3.5 py-2 font-semibold">{String(s.stage)}</td>
                    <td className="py-2 pr-3">
                      <div className="tabular-nums" style={{ fontFamily: "var(--mono)" }}>
                        {Number(s.duration_ms).toFixed(1)}ms
                      </div>
                      <div
                        aria-hidden
                        className="mt-1 h-1 w-24 overflow-hidden rounded-full"
                        style={{ background: "var(--page)" }}
                      >
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${Math.max(3, (Number(s.duration_ms) / maxMs) * 100)}%`,
                            background: "var(--accent)",
                            opacity: 0.55,
                          }}
                        />
                      </div>
                    </td>
                    <td className="py-2 pr-3.5" style={{ color: "var(--ink-soft)" }}>
                      {Object.entries(s)
                        .filter(([k]) => !["stage", "duration_ms", "span_id", "trace_id", "input", "output"].includes(k))
                        .map(([k, v]) => `${k}=${String(v)}`)
                        .join("  ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}

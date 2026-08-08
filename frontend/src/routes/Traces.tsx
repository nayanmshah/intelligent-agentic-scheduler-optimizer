import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

/**
 * Trace and replay. Reads the in-process store only (FR-087) -- with the container
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

  return (
    <main className="mx-auto grid max-w-6xl grid-cols-[1fr_1.4fr] gap-4 p-5">
      <section>
        <h1 className="mb-2 text-lg font-semibold">Decisions</h1>
        <ul className="flex flex-col gap-1">
          {traces.data?.decisions.map((d) => (
            <li key={d.id}>
              <button
                onClick={() => {
                  setSelected(d.trace_id);
                  setReplay(null);
                }}
                className="w-full rounded border px-2 py-1.5 text-left text-xs"
                style={{
                  borderColor: selected === d.trace_id ? "var(--accent)" : "var(--line)",
                  background: "var(--surface)",
                }}
              >
                <div className="truncate">{d.raw_text}</div>
                <div className="mt-0.5" style={{ color: "var(--ink-soft)" }}>
                  {d.offers} offers
                  {d.question && " · asked a question"}
                  {d.fallback_fired.length > 0 && ` · fallback: ${d.fallback_fired.join(",")}`}
                </div>
              </button>
              {selected === d.trace_id && (
                <button
                  onClick={() => api.replay(d.id).then(setReplay)}
                  className="mt-1 rounded border px-2 py-1 text-[0.65rem]"
                  style={{ borderColor: "var(--line)" }}
                >
                  Replay and check byte equality
                </button>
              )}
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2 className="mb-2 text-lg font-semibold">Spans</h2>
        {replay && (
          <p
            className="mb-2 rounded border p-2 text-xs"
            style={{ borderColor: replay.identical ? "var(--accent)" : "var(--warn)" }}
          >
            {replay.identical
              ? "Replay reproduced the decision byte for byte."
              : "Replay differed — see the field-level diff in the response."}
          </p>
        )}
        {spans.data && (
          <table className="w-full text-xs">
            <thead style={{ color: "var(--ink-soft)" }}>
              <tr className="text-left">
                <th className="py-1">stage</th>
                <th>ms</th>
                <th>detail</th>
              </tr>
            </thead>
            <tbody>
              {spans.data.spans.map((s, i) => (
                <tr key={i} className="border-t" style={{ borderColor: "var(--line)" }}>
                  <td className="py-1 font-medium">{String(s.stage)}</td>
                  <td className="tabular-nums">{Number(s.duration_ms).toFixed(1)}</td>
                  <td style={{ color: "var(--ink-soft)" }}>
                    {Object.entries(s)
                      .filter(([k]) => !["stage", "duration_ms", "span_id", "trace_id"].includes(k))
                      .map(([k, v]) => `${k}=${String(v)}`)
                      .join("  ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}

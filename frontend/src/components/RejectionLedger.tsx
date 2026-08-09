import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type LedgerGroup, type WhyAnswer } from "@/lib/api";

/**
 * FR-030 / FR-031. Collapsed by default, expandable in one click.
 *
 * This is the most domain-credible surface in the product — it answers the
 * patient's "but isn't 3 o'clock open?" without opening a calendar — and it stays
 * shut until asked for, because the operator's decision surface must stay at three
 * choices even though the evidence behind them is complete.
 *
 * Each row carries a magnitude bar scaled to the largest cause, so the shape of
 * "where did 13,000 candidates go?" is visible before any number is read.
 */
export function RejectionLedger({
  groups,
  decisionId,
}: {
  groups: LedgerGroup[];
  decisionId: string;
}) {
  const [open, setOpen] = useState(false);
  const total = groups.reduce((n, g) => n + g.count, 0);
  const max = groups.reduce((n, g) => Math.max(n, g.count), 1);
  if (!total) return null;

  return (
    <section className="card overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2.5 px-4 py-3 text-left text-sm transition-colors hover:bg-[var(--accent-faint)]"
        aria-expanded={open}
      >
        <span
          aria-hidden
          className="text-[0.7rem] transition-transform"
          style={{
            color: "var(--ink-faint)",
            transform: open ? "rotate(90deg)" : "none",
            display: "inline-block",
          }}
        >
          ▸
        </span>
        <span className="font-medium">Considered and rejected</span>
        <span
          className="rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums"
          style={{ background: "var(--accent-soft)", color: "var(--accent-deep)" }}
        >
          {total.toLocaleString()}
        </span>
        <span className="ml-auto text-[0.68rem]" style={{ color: "var(--ink-faint)" }}>
          the evidence, one click away
        </span>
      </button>
      {open && (
        <ul className="border-t px-4 py-2" style={{ borderColor: "var(--line)" }}>
          {groups.map((g) => (
            <li key={g.reason} className="flex items-center gap-3 py-1.5 text-xs">
              <span className="w-16 shrink-0 text-right font-bold tabular-nums">
                {g.count.toLocaleString()}
              </span>
              <span
                aria-hidden
                className="h-1.5 w-24 shrink-0 overflow-hidden rounded-full"
                style={{ background: "var(--page)" }}
              >
                <span
                  className="block h-full rounded-full"
                  style={{
                    width: `${Math.max(4, (g.count / max) * 100)}%`,
                    background: "var(--accent)",
                    opacity: 0.5,
                  }}
                />
              </span>
              {/* Plain language, single cause, no jargon — lint-enforced. */}
              <span style={{ color: "var(--ink-soft)" }}>{g.sentence}</span>
            </li>
          ))}
          <SlotLookup decisionId={decisionId} />
        </ul>
      )}
    </section>
  );
}

/**
 * FR-109 — "but isn't 3 o'clock free?", answered for that one time.
 *
 * The rows above group every rejection by cause, which is the right shape for "where
 * did 13,000 candidates go?" and the wrong shape for the question a patient actually
 * asks, which is about one time. Both grains matter; only this one ends a phone call.
 *
 * Options come from the server so every time offered is on the real grid and inside
 * real business hours — "why not 3:07?" has no honest answer on a ten-minute grid.
 */
function verdict(a: WhyAnswer): string {
  const outranked = Math.max(0, a.bookable - a.offered);
  if (a.bookable === 0) return `Nothing was bookable at ${a.at}.`;
  if (a.offered === 0) {
    return `${a.bookable} ${a.bookable === 1 ? "was" : "were"} bookable — outranked by the times offered above.`;
  }
  if (outranked === 0) {
    return a.offered === 1
      ? "This is one of the times offered above."
      : `These are ${a.offered} of the times offered above.`;
  }
  return `${a.offered} of ${a.offered === 1 ? "these is" : "these are"} offered above; ${outranked} more ${
    outranked === 1 ? "was" : "were"
  } bookable but outranked.`;
}

function SlotLookup({ decisionId }: { decisionId: string }) {
  const { data: options } = useQuery({
    queryKey: ["why-options", decisionId],
    queryFn: () => api.whyOptions(decisionId),
  });
  const [day, setDay] = useState("");
  const [at, setAt] = useState("");

  // Default to the first searched day, and a mid-afternoon time on it.
  useEffect(() => {
    if (!options?.days.length || day) return;
    const first = options.default_day ?? options.days[0]!.value;
    setDay(first);
    const times = options.times[first] ?? [];
    const mid = times[Math.floor(times.length / 2)];
    setAt((times.find((t) => t.value === "15:00") ?? mid)?.value ?? "");
  }, [options, day]);

  const { data: answer, isFetching } = useQuery({
    queryKey: ["why", decisionId, day, at],
    queryFn: () => api.why(decisionId, at, day),
    enabled: Boolean(day && at),
  });

  const times = options?.times[day] ?? [];
  const select =
    "rounded-md border px-2 py-1 text-xs font-medium tabular-nums";
  const selectStyle = { borderColor: "var(--line)", background: "var(--surface)" };

  return (
    <li className="mt-2 border-t pt-3" style={{ borderColor: "var(--line)" }}>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="label-caps">Why not…</span>
        <select
          className={select}
          style={selectStyle}
          value={at}
          onChange={(e) => setAt(e.target.value)}
          aria-label="Time to ask about"
        >
          {times.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
        <select
          className={select}
          style={selectStyle}
          value={day}
          onChange={(e) => setDay(e.target.value)}
          aria-label="Day to ask about"
        >
          {(options?.days ?? []).map((d) => (
            <option key={d.value} value={d.value}>{d.label}</option>
          ))}
        </select>
        {isFetching && <span style={{ color: "var(--ink-faint)" }}>checking…</span>}
      </div>

      {answer && (
        <div className="mt-2.5 rounded-lg p-3" style={{ background: "var(--accent-faint)" }}>
          <p className="text-xs font-semibold">
            {answer.considered.toLocaleString()} combination
            {answer.considered === 1 ? "" : "s"} at {answer.at}, {answer.day_label}
          </p>
          {answer.considered === 0 ? (
            <p className="mt-1.5 text-xs" style={{ color: "var(--ink-soft)" }}>
              No appointment of this type could start then — it falls outside the search.
            </p>
          ) : (
            <ul className="mt-1.5 space-y-1">
              {answer.causes.map((c) => (
                <li key={c.reason} className="flex gap-3 text-xs">
                  <span className="w-8 shrink-0 text-right font-bold tabular-nums">{c.count}</span>
                  <span style={{ color: "var(--ink-soft)" }}>{c.sentence}</span>
                </li>
              ))}
            </ul>
          )}
          {/* Three different endings, because they are three different answers and
              only one is a refusal. The third exists because the most natural thing an
              operator does is ask about a time that IS on screen — calling that
              "outranked" would be false about the card they are looking at. */}
          {answer.considered > 0 && (
            <p className="mt-2 text-xs font-medium" style={{ color: "var(--accent-deep)" }}>
              {verdict(answer)}
            </p>
          )}
        </div>
      )}
    </li>
  );
}

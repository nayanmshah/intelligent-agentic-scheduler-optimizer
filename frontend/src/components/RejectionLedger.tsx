import { useState } from "react";
import type { LedgerGroup } from "@/lib/api";

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
export function RejectionLedger({ groups }: { groups: LedgerGroup[] }) {
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
        </ul>
      )}
    </section>
  );
}

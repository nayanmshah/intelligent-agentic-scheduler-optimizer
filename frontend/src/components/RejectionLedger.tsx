import { useState } from "react";
import type { LedgerGroup } from "@/lib/api";

/**
 * FR-030 / FR-031. Collapsed by default, expandable in one click.
 *
 * This is the most domain-credible surface in the product -- it answers the
 * patient's "but isn't 3 o'clock open?" without opening a calendar -- and it stays
 * shut until asked for, because the operator's decision surface must stay at three
 * choices even though the evidence behind them is complete.
 */
export function RejectionLedger({ groups }: { groups: LedgerGroup[] }) {
  const [open, setOpen] = useState(false);
  const total = groups.reduce((n, g) => n + g.count, 0);
  if (!total) return null;

  return (
    <section className="rounded border" style={{ borderColor: "var(--line)", background: "var(--surface)" }}>
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm"
        aria-expanded={open}
      >
        <span aria-hidden>{open ? "▾" : "▸"}</span>
        Considered and rejected ({total.toLocaleString()})
      </button>
      {open && (
        <ul className="border-t px-3 py-2 text-xs" style={{ borderColor: "var(--line)" }}>
          {groups.map((g) => (
            <li key={g.reason} className="flex gap-3 py-1">
              <span className="w-14 shrink-0 text-right font-semibold tabular-nums">
                {g.count.toLocaleString()}
              </span>
              {/* Plain language, single cause, no jargon -- lint-enforced. */}
              <span>{g.sentence}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

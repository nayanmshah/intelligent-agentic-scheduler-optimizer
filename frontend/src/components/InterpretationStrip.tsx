import { useState } from "react";
import type { InterpretationField } from "@/lib/api";

const LABELS: Record<string, string> = {
  date_range: "When",
  time_window: "Time",
  urgency: "Urgency",
  provider_preference: "Provider",
  appointment_type: "Visit",
  exclusions: "Avoid",
};

function display(f: InterpretationField): string {
  const v = f.value as Record<string, unknown> | string | null;
  if (v === null || v === undefined) return "any";
  if (typeof v === "string") return v;
  if (typeof v === "object") {
    if ("start" in v && "end" in v) {
      const s = String(v.start), e = String(v.end);
      return s === e ? s : `${s} → ${e}`;
    }
    if ("start_min" in v || "end_min" in v) {
      const fmt = (m: unknown) =>
        m === null || m === undefined ? null : `${Math.floor(Number(m) / 60)}:${String(Number(m) % 60).padStart(2, "0")}`;
      const a = fmt(v.start_min), b = fmt(v.end_min);
      if (!a && !b) return "any time";
      return `${a ?? "open"} – ${b ?? "close"}`;
    }
    if ("weekdays" in v) {
      const days = (v.weekdays as number[]) ?? [];
      const names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
      return days.length ? days.map((d) => names[d]).join(", ") : "nothing";
    }
  }
  return String(v);
}

function band(confidence: number): { label: string; tone: string } {
  if (confidence >= 0.85) return { label: "high", tone: "var(--ink-soft)" };
  if (confidence >= 0.6) return { label: "medium", tone: "var(--warn)" };
  return { label: "low", tone: "var(--warn)" };
}

/**
 * FR-002 / FR-003 / FR-067. One chip per extracted field: the resolved value, a
 * confidence band, and the **verbatim words it came from**.
 *
 * The provenance is not decoration. It is what lets an operator trust the search
 * without re-reading the request -- and it is the surface that catches the ranked #1
 * failure mode, a confidently-wrong "after 3" read as 03:00.
 */
export function InterpretationStrip({ fields }: { fields: InterpretationField[] }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div className="flex flex-wrap items-start gap-2">
      {fields.map((f) => {
        const b = band(f.confidence);
        const isOpen = open === f.name;
        return (
          <button
            key={f.name}
            onClick={() => setOpen(isOpen ? null : f.name)}
            className="rounded border px-2 py-1 text-left text-xs"
            style={{ borderColor: "var(--line)", background: "var(--surface)" }}
            aria-expanded={isOpen}
          >
            <span style={{ color: "var(--ink-soft)" }}>{LABELS[f.name] ?? f.name}: </span>
            <span className="font-medium">{display(f)}</span>
            <span className="ml-1" style={{ color: b.tone }}>
              ·{b.label}
            </span>
            {isOpen && (
              <span className="mt-1 block text-[0.65rem]" style={{ color: "var(--ink-soft)" }}>
                {f.span ? (
                  <>from “{f.span.text}”</>
                ) : (
                  <>derived · {f.derived_rule}</>
                )}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

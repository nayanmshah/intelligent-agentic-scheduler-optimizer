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
  if (typeof v === "string") {
    // Ids stay honest in the tooltip/provenance; the chip shows the human form.
    if (f.name === "provider_preference" && v.startsWith("prov-")) {
      const name = v.slice(5);
      return name.charAt(0).toUpperCase() + name.slice(1);
    }
    if (f.name === "appointment_type") return v.replaceAll("_", " ");
    return v;
  }
  if (typeof v === "object") {
    if ("start" in v && "end" in v) {
      const s = String(v.start), e = String(v.end);
      return s === e ? s : `${s} → ${e}`;
    }
    if ("start_min" in v || "end_min" in v) {
      const fmt = (m: unknown) =>
        m === null || m === undefined
          ? null
          : `${Math.floor(Number(m) / 60)}:${String(Number(m) % 60).padStart(2, "0")}`;
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

/** Three-dot confidence meter + the word, so colour is never the only signal. */
function Confidence({ value }: { value: number }) {
  const level = value >= 0.85 ? 3 : value >= 0.6 ? 2 : 1;
  const label = level === 3 ? "high" : level === 2 ? "medium" : "low";
  const tone = level === 3 ? "var(--accent)" : "var(--warn)";
  return (
    <span className="inline-flex items-center gap-1" title={`confidence ${value.toFixed(2)}`}>
      <span aria-hidden className="inline-flex items-center gap-[2px]">
        {[1, 2, 3].map((i) => (
          <span
            key={i}
            className="inline-block h-1 w-1 rounded-full"
            style={{ background: i <= level ? tone : "var(--line-strong)" }}
          />
        ))}
      </span>
      <span className="text-[0.62rem]" style={{ color: level === 3 ? "var(--ink-faint)" : tone }}>
        {label}
      </span>
    </span>
  );
}

/**
 * FR-002 / FR-003 / FR-067. One chip per extracted field: the resolved value, a
 * confidence meter, and — one click away — the **verbatim words it came from**.
 *
 * The provenance is not decoration. It is what lets an operator trust the search
 * without re-reading the request, and it is the surface that catches the ranked #1
 * failure mode: a confidently-wrong "after 3" read as 03:00.
 */
export function InterpretationStrip({ fields }: { fields: InterpretationField[] }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div className="flex flex-wrap items-start gap-2">
      {fields.map((f) => {
        const isOpen = open === f.name;
        return (
          <button
            key={f.name}
            onClick={() => setOpen(isOpen ? null : f.name)}
            className="rounded-lg border px-2.5 py-1.5 text-left text-xs transition-colors"
            style={{
              borderColor: isOpen ? "var(--accent)" : "var(--line)",
              background: "var(--surface)",
              boxShadow: "0 1px 2px rgba(16,27,36,0.04)",
            }}
            aria-expanded={isOpen}
          >
            <span className="flex items-center gap-2">
              <span className="label-caps">{LABELS[f.name] ?? f.name}</span>
              <span className="font-semibold">{display(f)}</span>
              <Confidence value={f.confidence} />
            </span>
            {isOpen && (
              <span
                className="mt-1.5 block border-t pt-1.5 text-[0.68rem]"
                style={{ borderColor: "var(--line)", color: "var(--ink-soft)" }}
              >
                {f.span ? (
                  <>
                    from{" "}
                    <em className="not-italic" style={{ fontFamily: "var(--serif)" }}>
                      “{f.span.text}”
                    </em>
                  </>
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

import type { Funnel } from "@/lib/api";

/**
 * FR-029. Four live numbers that reconcile with the conservation invariant.
 *
 * They are worth showing precisely *because* the backend asserts
 * `feasible + Σ rejected == enumerated` after every stage. Without that assertion
 * these would be decoration; with it, they are the answer to "did it miss anything?".
 */
export function FunnelCounter({ funnel }: { funnel: Funnel }) {
  const steps = [
    { label: "considered", value: funnel.enumerated },
    { label: "bookable", value: funnel.feasible },
    { label: "in window", value: funnel.in_tier },
    { label: "offered", value: funnel.offered },
  ];
  return (
    <div className="flex items-center gap-3">
      {steps.map((s, i) => (
        <span key={s.label} className="flex items-center gap-3">
          {i > 0 && (
            <span aria-hidden className="text-sm" style={{ color: "var(--ink-faint)" }}>
              →
            </span>
          )}
          <span className="flex flex-col leading-tight">
            <strong
              className="text-[0.95rem] font-bold tabular-nums tracking-tight"
              style={{ color: i === steps.length - 1 ? "var(--accent)" : "var(--ink)" }}
            >
              {s.value.toLocaleString()}
            </strong>
            <span className="label-caps">{s.label}</span>
          </span>
        </span>
      ))}
      <span className="ml-2 self-end pb-0.5 text-[0.62rem]" style={{ color: "var(--ink-faint)" }}>
        {funnel.grid_slots.toLocaleString()} slots × eligible providers
      </span>
    </div>
  );
}

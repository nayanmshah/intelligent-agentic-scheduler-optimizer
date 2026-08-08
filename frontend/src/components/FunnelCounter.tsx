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
    <div className="flex items-center gap-2 text-xs" style={{ color: "var(--ink-soft)" }}>
      {steps.map((s, i) => (
        <span key={s.label} className="inline-flex items-center gap-2">
          {i > 0 && <span aria-hidden>→</span>}
          <span>
            <strong className="font-semibold" style={{ color: "var(--ink)" }}>
              {s.value.toLocaleString()}
            </strong>{" "}
            {s.label}
          </span>
        </span>
      ))}
      <span className="ml-2 text-[0.65rem]">
        ({funnel.grid_slots.toLocaleString()} slots × eligible providers)
      </span>
    </div>
  );
}

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ContributionBar } from "../ContributionBar";
import { FunnelCounter } from "../FunnelCounter";
import { InterpretationStrip } from "../InterpretationStrip";
import { StabilityIndicator } from "../StabilityIndicator";
import type { Contribution, InterpretationField } from "@/lib/api";

const CONTRIBUTIONS: Contribution[] = [
  { axis: "time_fit", value: 1.0, weight: 0.35, weighted: 0.35 },
  { axis: "continuity", value: 0.7, weight: 0.25, weighted: 0.175 },
  { axis: "efficiency", value: 0.8, weight: 0.25, weighted: 0.2 },
  { axis: "prime_time", value: 1.0, weight: 0.15, weighted: 0.15 },
];

describe("ContributionBar", () => {
  it("never shows a naked number -- the total appears with its parts", () => {
    render(<ContributionBar contributions={CONTRIBUTIONS} score={0.875} />);
    expect(screen.getByText("= 88%")).toBeInTheDocument();
    for (const label of ["Time fit", "Continuity", "Efficiency", "Block protection"]) {
      expect(screen.getByText(new RegExp(label))).toBeInTheDocument();
    }
  });

  it("labels every segment, so greyscale stays interpretable (NFR-24)", () => {
    render(<ContributionBar contributions={CONTRIBUTIONS} score={0.875} />);
    const bar = screen.getByRole("img");
    expect(bar.getAttribute("aria-label")).toContain("Time fit");
  });
});

describe("FunnelCounter", () => {
  it("shows all four live numbers (FR-029)", () => {
    render(
      <FunnelCounter
        funnel={{ grid_slots: 3348, enumerated: 13392, feasible: 133, in_tier: 5, offered: 3 }}
      />,
    );
    expect(screen.getByText("13,392")).toBeInTheDocument();
    expect(screen.getByText("133")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });
});

describe("InterpretationStrip", () => {
  const fields: InterpretationField[] = [
    {
      name: "time_window",
      value: { start_min: 900, end_min: null },
      confidence: 0.9,
      derived: false,
      derived_rule: null,
      span: { text: "after 3", start: 27, end: 34 },
    },
    {
      name: "urgency",
      value: "routine",
      confidence: 0.7,
      derived: true,
      derived_rule: "appointment-type-default-urgency",
      span: null,
    },
  ];

  it("renders the resolved value and a confidence band", () => {
    render(<InterpretationStrip fields={fields} />);
    expect(screen.getByText("15:00 – close")).toBeInTheDocument();
    expect(screen.getByText(/·high/)).toBeInTheDocument();
    expect(screen.getByText(/·medium/)).toBeInTheDocument();
  });
});

describe("StabilityIndicator", () => {
  it("states the result in words, not just a number (FR-081)", () => {
    render(
      <StabilityIndicator
        sentence="These three stay in the top 3 across 78% of sampled weight vectors."
        pct={78}
        samples={200}
      />,
    );
    expect(screen.getByText(/stay in the top 3/)).toBeInTheDocument();
    expect(screen.getByText("78%")).toBeInTheDocument();
  });
});

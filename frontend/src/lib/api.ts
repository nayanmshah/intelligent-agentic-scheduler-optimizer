/** Wire types and fetch helpers. Mirrors backend/app/api/schemas.py. */

export type Contribution = {
  axis: string;
  value: number;
  weight: number;
  weighted: number;
};

export type Offer = {
  candidate_id: string;
  weekday: string;
  date_display: string;
  start_display: string;
  provider_name: string;
  operatory_name: string;
  duration_min: number;
  type_name: string;
  score: number;
  contributions: Contribution[];
  reason: string;
  template_reason: string;
  llm_reason: string | null;
  gate_fired: boolean;
  coequal_group: number | null;
  is_overflow: boolean;
  emergency_hold_released: boolean;
};

export type InterpretationField = {
  name: string;
  value: unknown;
  confidence: number;
  derived: boolean;
  derived_rule: string | null;
  span: { text: string; start: number; end: number } | null;
};

export type Funnel = {
  grid_slots: number;
  enumerated: number;
  feasible: number;
  in_tier: number;
  offered: number;
};

export type LedgerGroup = { reason: string; count: number; sentence: string };

export type Decision = {
  id: string;
  trace_id: string;
  raw_text: string;
  origin_state: "offered" | "offered_overflow";
  question: string | null;
  flags: string[];
  limited_availability: boolean;
  interpretation: InterpretationField[];
  funnel: Funnel | null;
  offers: Offer[];
  overflow: Offer[];
  ledger: LedgerGroup[];
  counterfactual: { sentence: string; gain: number } | null;
  weights: {
    profile_id: string;
    nominal: Record<string, number> | null;
    effective: Record<string, number> | null;
  };
  fallback_fired: string[];
};

export type Reference = {
  reference_now: string;
  network: string;
  llm_mode: string;
  opik_enabled: boolean;
  agents: Record<string, string>;
  seed_anomalies: string;
};

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  reference: () => json<Reference>("/api/reference"),
  preflight: () => json<{ ready: boolean; checks: { name: string; status: string; detail: string }[] }>("/api/preflight"),
  submit: (text: string, patientId: string | null) =>
    json<Decision>("/api/requests", {
      method: "POST",
      body: JSON.stringify({ text, patient_id: patientId }),
    }),
  answer: (id: string, choice: string) =>
    json<Decision>(`/api/requests/${id}/answer`, {
      method: "POST",
      body: JSON.stringify({ choice }),
    }),
  book: (requestId: string, candidateId: string) =>
    json<{ confirmation: string; is_override: boolean }>("/api/bookings", {
      method: "POST",
      body: JSON.stringify({ request_id: requestId, candidate_id: candidateId }),
    }),
  reset: () => json<{ traces_retained: number }>("/api/session/reset", { method: "POST" }),
  profiles: () => json<{ active: string; profiles: { id: string; name: string; weights: Record<string, number>; is_fitted: boolean }[] }>("/api/policy/profiles"),
  setProfile: (id: string) =>
    json<{ active: string }>("/api/policy/active", { method: "PUT", body: JSON.stringify({ id }) }),
  rerank: (requestId: string, weights: Record<string, number>) =>
    json<{ llm_calls: number; ranked: { candidate_id: string; score: number; provider_name: string | null; start_display: string | null }[] }>(
      "/api/policy/rerank",
      { method: "POST", body: JSON.stringify({ request_id: requestId, weights }) },
    ),
  stability: (requestId: string) =>
    json<{ held_pct: number; sentence: string; samples: number; per_slot_pct: Record<string, number> }>(
      `/api/policy/stability?request_id=${requestId}`,
    ),
  traces: () => json<{ decisions: { id: string; trace_id: string; raw_text: string; offers: number; fallback_fired: string[]; question: string | null }[] }>("/api/traces"),
  trace: (traceId: string) =>
    json<{ trace_id: string; spans: Record<string, unknown>[] }>(`/api/traces/${traceId}`),
  replay: (decisionId: string) =>
    json<{ identical: boolean; diff: unknown }>(`/api/traces/${decisionId}/replay`, { method: "POST" }),
};

export const AXIS_LABELS: Record<string, string> = {
  time_fit: "Time fit",
  continuity: "Continuity",
  efficiency: "Efficiency",
  prime_time: "Block protection",
};

/** Distinguishable in greyscale, per NFR-24 -- the bar must not rely on colour. */
export const AXIS_STYLE: Record<string, { fill: string; pattern: string }> = {
  time_fit: { fill: "#1f5f8b", pattern: "solid" },
  continuity: { fill: "#4d8fac", pattern: "solid" },
  efficiency: { fill: "#8fb8c9", pattern: "solid" },
  prime_time: { fill: "#c9dbe4", pattern: "solid" },
};

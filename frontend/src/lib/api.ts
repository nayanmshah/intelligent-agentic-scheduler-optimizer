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

/** FR-109: the per-time answer to "but isn't 3 o'clock free?" */
export type WhyOptions = {
  days: { value: string; label: string }[];
  times: Record<string, { value: string; label: string }[]>;
  default_day: string | null;
};

export type WhyAnswer = {
  day: string;
  day_label: string;
  at: string;
  considered: number;
  bookable: number;
  offered: number;
  causes: { reason: string; count: number; sentence: string }[];
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
  /** FR-110: how the words arrived. "voice" means a confirmed transcript. */
  source: "text" | "voice";
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
  /** "system" (real time, the default) or "frozen" (pinned to the dataset). */
  clock: string;
  network: string;
  llm_mode: string;
  /** FR-110. False turns dictation off without a rebuild; the browser decides the rest. */
  voice_input: boolean;
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
  whyOptions: (id: string) => json<WhyOptions>(`/api/requests/${id}/why-options`),
  why: (id: string, at: string, day: string) =>
    json<WhyAnswer>(`/api/requests/${id}/why?at=${encodeURIComponent(at)}&day=${day}`),
  preflight: () => json<{ ready: boolean; checks: { name: string; status: string; detail: string }[] }>("/api/preflight"),
  submit: (text: string, patientId: string | null, source: "text" | "voice" = "text") =>
    json<Decision>("/api/requests", {
      method: "POST",
      body: JSON.stringify({ text, patient_id: patientId, source }),
    }),

  /**
   * The same decision, with each stage reported as it finishes.
   *
   * A live request is three sequential model calls and takes ~15 seconds. Without
   * this the console shows a "…" for that long, which reads as frozen — and hides
   * the one thing worth seeing.
   *
   * Server-Sent Events over `fetch` rather than `EventSource`, because the request
   * carries a body and `EventSource` is GET-only.
   */
  submitStream: async (
    text: string,
    patientId: string | null,
    source: "text" | "voice",
    onStage: (s: StageEvent) => void,
  ): Promise<Decision> => {
    const res = await fetch("/api/requests/stream", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ text, patient_id: patientId, source }),
    });
    if (!res.ok || !res.body) throw new Error(await res.text().catch(() => res.statusText));

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let decision: Decision | null = null;

    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // Frames are separated by a blank line; a partial frame stays in the buffer
      // until the rest of it arrives.
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        let event = "message";
        let data = "";
        for (const line of frame.split("\n")) {
          if (line.startsWith("event: ")) event = line.slice(7);
          else if (line.startsWith("data: ")) data += line.slice(6);
        }
        if (!data) continue;
        const payload = JSON.parse(data);
        if (event === "pending" || event === "stage") onStage({ ...payload, done: event === "stage" });
        else if (event === "decision") decision = payload as Decision;
        else if (event === "error") throw new Error(payload.detail ?? "request failed");
      }
    }
    if (!decision) throw new Error("the stream ended before a decision arrived");
    return decision;
  },
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
    json<{
      llm_calls: number;
      ranked: {
        candidate_id: string;
        score: number;
        provider_name: string | null;
        start_display: string | null;
        /** False when this weighting promoted a slot that was not originally offered. */
        was_offered: boolean;
      }[];
    }>(
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

export type StageEvent = {
  stage: string;
  label: string;
  /** True once the stage has finished; false while it is still announced-but-pending. */
  done: boolean;
  ms?: number;
  implementation?: string | null;
  fallback_fired?: boolean;
};

export const AXIS_LABELS: Record<string, string> = {
  time_fit: "Time fit",
  continuity: "Continuity",
  efficiency: "Efficiency",
  prime_time: "Block protection",
};

/** Distinguishable in greyscale, per NFR-24 -- the bar must not rely on colour. */
export const AXIS_STYLE: Record<string, { fill: string; pattern: string }> = {
  // A single-hue teal ramp: ordered lightness carries the identity, so the bar
  // stays readable in greyscale (NFR-24) and matches the product accent.
  time_fit: { fill: "#0d6a60", pattern: "solid" },
  continuity: { fill: "#3d8c7f", pattern: "solid" },
  efficiency: { fill: "#77afa3", pattern: "solid" },
  prime_time: { fill: "#b5d3cb", pattern: "solid" },
};

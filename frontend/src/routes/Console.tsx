import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api, type Decision, type Offer } from "@/lib/api";
import { InterpretationStrip } from "@/components/InterpretationStrip";
import { FunnelCounter } from "@/components/FunnelCounter";
import { OfferCard } from "@/components/OfferCard";
import { RejectionLedger } from "@/components/RejectionLedger";

const EXAMPLES = [
  "Can I come in next Thursday after 3? Prefer Sarah if she's around.",
  "I need something first thing tomorrow, it's urgent",
  "Whatever works next week, I have PT on Tuesdays",
  "My tooth's been bothering me since Friday",
];

/**
 * The operator console.
 *
 * Information hierarchy, per development-plan §4: the three cards are the visual
 * centre, the evidence is exactly one click away and never on screen by default,
 * no number appears without its decomposition, and there is **no weight control on
 * this screen at any size** (FR-076) -- per-call fiddling would destroy the
 * consistency the product exists to provide.
 */
export default function Console() {
  const [text, setText] = useState("");
  const [decision, setDecision] = useState<Decision | null>(null);
  const [booked, setBooked] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const submit = useMutation({
    mutationFn: (t: string) => api.submit(t, "pat-000"),
    onSuccess: (d) => {
      setDecision(d);
      setBooked(null);
      setConfirmation(null);
    },
  });

  const answer = useMutation({
    mutationFn: (choice: string) => api.answer(decision!.id, choice),
    onSuccess: (d) => setDecision(d),
  });

  const book = useMutation({
    mutationFn: (o: Offer) => api.book(decision!.id, o.candidate_id),
    onSuccess: (r, o) => {
      setBooked(o.candidate_id);
      setConfirmation(r.confirmation);
    },
  });

  // Keyboard-first: the front desk is a keyboard job and a mouse round-trip is
  // dead air on a live call (NFR-25, FR-052).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = document.activeElement?.tagName === "TEXTAREA";
      if (typing && e.key !== "Enter") return;
      if (e.key === "Enter" && typing && !e.shiftKey) {
        e.preventDefault();
        if (text.trim()) submit.mutate(text);
        return;
      }
      if (!decision) return;
      const n = Number(e.key);
      if (n >= 1 && n <= decision.offers.length) {
        book.mutate(decision.offers[n - 1]!);
      }
      if (e.key.toLowerCase() === "e") inputRef.current?.focus();
      if (e.key.toLowerCase() === "r") {
        api.reset().then(() => {
          setDecision(null);
          setBooked(null);
          setConfirmation(null);
        });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [text, decision, submit, book]);

  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-4 p-5">
      {/* 1. Request box */}
      <section className="flex gap-3">
        <textarea
          ref={inputRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={2}
          placeholder="Type the patient's own words…"
          className="flex-1 rounded border p-2 text-sm"
          style={{ borderColor: "var(--line)", background: "var(--surface)" }}
        />
        <button
          onClick={() => text.trim() && submit.mutate(text)}
          disabled={submit.isPending}
          className="self-start rounded px-4 py-2 text-sm font-medium text-white"
          style={{ background: "var(--accent)" }}
        >
          {submit.isPending ? "…" : "Find times"}
        </button>
      </section>

      <div className="flex flex-wrap gap-2 text-xs">
        {EXAMPLES.map((e) => (
          <button
            key={e}
            onClick={() => {
              setText(e);
              submit.mutate(e);
            }}
            className="rounded border px-2 py-1"
            style={{ borderColor: "var(--line)", color: "var(--ink-soft)" }}
          >
            {e.length > 46 ? `${e.slice(0, 46)}…` : e}
          </button>
        ))}
      </div>

      {submit.isError && (
        <p className="text-sm" style={{ color: "var(--warn)" }}>
          {String(submit.error)}
        </p>
      )}

      {decision && (
        <>
          {/* 2. Interpretation strip */}
          <InterpretationStrip fields={decision.interpretation} />

          {decision.flags.map((f) => (
            <p key={f} className="text-xs" style={{ color: "var(--warn)" }}>
              {f}
            </p>
          ))}

          {/* Clarifying question renders INLINE, never as a modal -- nothing on the
              request path is gated behind a dialog, because a patient is waiting. */}
          {decision.question && (
            <section
              className="rounded border p-3"
              style={{ borderColor: "var(--warn)", background: "var(--surface)" }}
            >
              <p className="text-sm font-medium">{decision.question}</p>
              <div className="mt-2 flex gap-2">
                {decision.question
                  .replace(/^.*?\s(?:mean|for)\s/i, "")
                  .replace("?", "")
                  .split(" or ")
                  .map((chip) => (
                    <button
                      key={chip}
                      onClick={() => answer.mutate(chip.trim())}
                      className="rounded border px-3 py-1 text-sm"
                      style={{ borderColor: "var(--line)" }}
                    >
                      {chip.trim()}
                    </button>
                  ))}
              </div>
            </section>
          )}

          {/* 3. Funnel */}
          {decision.funnel && <FunnelCounter funnel={decision.funnel} />}

          {confirmation && (
            <p className="rounded border p-2 text-sm" style={{ borderColor: "var(--accent)" }}>
              {confirmation}
            </p>
          )}

          {/* 4. The decision */}
          <section className="grid grid-cols-3 gap-3">
            {decision.offers.map((o, i) => (
              <OfferCard
                key={o.candidate_id}
                offer={o}
                index={i + 1}
                onHold={(x) => book.mutate(x)}
                booked={booked === o.candidate_id}
              />
            ))}
          </section>

          {decision.limited_availability && (
            <p className="text-xs" style={{ color: "var(--warn)" }}>
              Limited availability — these are the only distinct options we found.
            </p>
          )}

          {decision.counterfactual && (
            <p className="text-sm">{decision.counterfactual.sentence}</p>
          )}

          {/* 5. Evidence, one click away */}
          <RejectionLedger groups={decision.ledger} />

          {decision.fallback_fired.length > 0 && (
            <p className="text-[0.65rem]" style={{ color: "var(--ink-soft)" }}>
              Deterministic fallback ran for: {decision.fallback_fired.join(", ")} — see Traces.
            </p>
          )}
        </>
      )}
    </main>
  );
}

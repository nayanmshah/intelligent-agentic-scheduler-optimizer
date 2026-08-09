import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api, type Decision, type Offer, type StageEvent } from "@/lib/api";
import { InterpretationStrip } from "@/components/InterpretationStrip";
import { FunnelCounter } from "@/components/FunnelCounter";
import { OfferCard } from "@/components/OfferCard";
import { RejectionLedger } from "@/components/RejectionLedger";
import { StageProgress } from "@/components/StageProgress";

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
 * this screen at any size** (FR-076) — per-call fiddling would destroy the
 * consistency the product exists to provide.
 */
export default function Console() {
  const [text, setText] = useState("");
  const [decision, setDecision] = useState<Decision | null>(null);
  const [booked, setBooked] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<string | null>(null);
  const [stages, setStages] = useState<StageEvent[]>([]);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const submit = useMutation({
    mutationFn: (t: string) => {
      // Clear the previous answer immediately: leaving the last decision on screen
      // while a new one runs invites reading a stale card as the fresh one.
      setDecision(null);
      setStages([]);
      return api.submitStream(t, "pat-000", (ev) =>
        setStages((prev) =>
          prev.some((s) => s.stage === ev.stage)
            ? prev.map((s) => (s.stage === ev.stage ? ev : s))
            : [...prev, ev],
        ),
      );
    },
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
    <main className="mx-auto flex max-w-[1120px] flex-col gap-5 px-6 py-7">
      {/* 1. The command bar — the patient's words, verbatim. */}
      <section className="card command-card overflow-hidden" style={{ boxShadow: "var(--shadow-raised)" }}>
        <div className="px-5 pt-4">
          <span className="label-caps">Patient request</span>
        </div>
        <textarea
          ref={inputRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={2}
          placeholder="Type the patient’s own words…"
          className="w-full resize-none border-none bg-transparent px-5 py-3 text-[1.15rem] leading-relaxed outline-none placeholder:italic"
          style={{ color: "var(--ink)" }}
        />
        <div
          className="flex items-center gap-3 border-t px-5 py-2.5"
          style={{ borderColor: "var(--line)", background: "var(--page)" }}
        >
          <span className="hidden items-center gap-3 text-[0.68rem] sm:flex" style={{ color: "var(--ink-faint)" }}>
            <span><span className="kbd">E</span> focus</span>
            <span><span className="kbd">↵</span> search</span>
            <span><span className="kbd">1</span>–<span className="kbd">3</span> hold</span>
            <span><span className="kbd">R</span> reset</span>
          </span>
          <button
            onClick={() => text.trim() && submit.mutate(text)}
            disabled={submit.isPending || !text.trim()}
            className="btn-primary ml-auto px-5 py-2 text-sm"
          >
            {submit.isPending ? "Searching…" : "Find times"}
          </button>
        </div>
      </section>

      {/* Example requests, one click from a cold start. */}
      {!decision && !submit.isPending && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="label-caps">Try</span>
          {EXAMPLES.map((e) => (
            <button
              key={e}
              onClick={() => {
                setText(e);
                submit.mutate(e);
              }}
              className="btn-quiet px-3 py-1.5 text-xs"
            >
              “{e.length > 46 ? `${e.slice(0, 46)}…` : e}”
            </button>
          ))}
        </div>
      )}

      {submit.isPending && <StageProgress stages={stages} />}

      {submit.isError && (
        <p
          className="card rise px-4 py-3 text-sm"
          style={{ borderColor: "var(--warn-line)", background: "var(--warn-bg)", color: "var(--warn)" }}
        >
          {String(submit.error)}
        </p>
      )}

      {decision && (
        <>
          {/* 2. What the system understood, with provenance one click away. */}
          <section className="rise flex flex-col gap-2">
            <span className="label-caps">How the request was read</span>
            <InterpretationStrip fields={decision.interpretation} />
          </section>

          {decision.flags.map((f) => (
            <p
              key={f}
              className="rise flex items-start gap-2.5 rounded-xl border px-4 py-3 text-sm"
              style={{ borderColor: "var(--warn-line)", background: "var(--warn-bg)", color: "var(--warn)" }}
            >
              <span aria-hidden className="mt-0.5 text-[0.8rem]">⚑</span>
              <span className="font-medium">{f}</span>
            </p>
          ))}

          {/* Clarifying question renders INLINE, never as a modal — nothing on the
              request path is gated behind a dialog, because a patient is waiting. */}
          {decision.question && (
            <section
              className="rise rounded-xl border-2 px-4 py-3"
              style={{ borderColor: "var(--accent)", background: "var(--accent-faint)" }}
            >
              <span className="label-caps" style={{ color: "var(--accent-deep)" }}>
                One question first
              </span>
              <p className="mt-1 text-[1.02rem] font-semibold">{decision.question}</p>
              <div className="mt-2.5 flex gap-2">
                {decision.question
                  .replace(/^.*?\s(?:mean|for)\s/i, "")
                  .replace("?", "")
                  .split(" or ")
                  .map((chip) => (
                    <button
                      key={chip}
                      onClick={() => answer.mutate(chip.trim())}
                      className="btn-primary px-4 py-1.5 text-sm"
                    >
                      {chip.trim()}
                    </button>
                  ))}
              </div>
            </section>
          )}

          {confirmation && (
            <p
              className="rise flex items-center gap-2.5 rounded-xl border px-4 py-3 text-sm font-medium"
              style={{ borderColor: "var(--ok-line)", background: "var(--ok-bg)", color: "var(--ok)" }}
            >
              <span aria-hidden>✓</span>
              {confirmation}
            </p>
          )}

          {/* 3. The decision, with its funnel on the same line of sight. */}
          <section className="rise mt-1 flex flex-wrap items-end justify-between gap-3">
            <h2 className="text-[1.05rem] font-bold tracking-tight">
              {decision.offers.length
                ? `Top ${decision.offers.length} of ${decision.funnel?.feasible.toLocaleString() ?? "the"} bookable times`
                : "No bookable times in the window"}
            </h2>
            {decision.funnel && <FunnelCounter funnel={decision.funnel} />}
          </section>

          <section className="grid grid-cols-3 gap-4">
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
            <p className="text-xs font-medium" style={{ color: "var(--warn)" }}>
              Limited availability — these are the only distinct options we found.
            </p>
          )}

          {decision.counterfactual && (
            <p className="read-aloud text-sm">{decision.counterfactual.sentence}</p>
          )}

          {/* 4. Evidence, one click away. */}
          <RejectionLedger groups={decision.ledger} />

          {decision.fallback_fired.length > 0 && (
            <p className="text-[0.68rem]" style={{ color: "var(--ink-faint)" }}>
              Deterministic fallback ran for: {decision.fallback_fired.join(", ")} — see Traces.
            </p>
          )}
        </>
      )}
    </main>
  );
}

import { Routes, Route, NavLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { SeatIndicator } from "@/components/SeatIndicator";
import Console from "@/routes/Console";
import Policy from "@/routes/Policy";
import Traces from "@/routes/Traces";

const NAV = [
  { to: "/", label: "Console" },
  { to: "/policy", label: "Policy" },
  { to: "/traces", label: "Traces" },
] as const;

/**
 * Persistent header (FR-104, FR-105, FR-108) — a dark instrument band.
 *
 * A user reading "Thursday the 13th" needs to know the dataset's today is Monday
 * the 10th, or every date on screen looks wrong. The mode indicator is here for the
 * same reason: which path produced this answer is never a guess. The dark band is
 * deliberate framing: status lives up here, work happens on the paper below.
 */
function ReferenceBar() {
  const { data } = useQuery({ queryKey: ["reference"], queryFn: api.reference });
  const [presentation, setPresentation] = useState(false);

  useEffect(() => {
    document.documentElement.dataset.presentation = presentation ? "on" : "off";
  }, [presentation]);

  const degraded = data?.network === "offline";
  // The clock is implicit: an application scheduling real days runs on today's
  // date, and saying so would be noise. The one exception is the simulated clock
  // (tests, CI, a demo outside the dataset window) — dates on screen are then NOT
  // today's, and hiding that would be a lie worse than the clutter.
  const simulated = data?.clock === "frozen";

  return (
    <header
      className="flex items-center gap-5 px-6 py-3"
      style={{
        background: "var(--bar)",
        borderBottom: "1px solid var(--bar-line)",
        color: "var(--bar-ink)",
      }}
    >
      {/* Wordmark. One string; rename at will. */}
      <div className="flex items-baseline gap-2">
        <span className="text-[1.05rem] font-bold tracking-tight">Chairside</span>
        <span
          className="hidden text-[0.68rem] tracking-wide sm:inline"
          style={{ color: "var(--bar-soft)" }}
        >
          agentic scheduling
        </span>
      </div>

      <span aria-hidden className="h-5 w-px" style={{ background: "var(--bar-line)" }} />

      {simulated && (
        <span
          className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium"
          style={{ background: "var(--warn-bg)", color: "var(--warn)" }}
          title="The clock is pinned to the dataset's reference instant. Dates on screen are relative to it, not to today."
        >
          Simulated clock ·{" "}
          {data?.reference_now
            ? new Date(data.reference_now).toLocaleDateString("en-US", {
                weekday: "short", month: "short", day: "numeric",
              })
            : "…"}
        </span>
      )}

      {/* Which path answered (FR-105). Degradation is amber, never hidden. */}
      <span
        className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium"
        style={
          degraded
            ? { background: "var(--warn-bg)", color: "var(--warn)" }
            : { background: "rgba(80, 200, 175, 0.12)", color: "#7fd4c4" }
        }
        title={
          degraded
            ? "No model in use: answers come from committed fixtures and deterministic rules."
            : "Extraction, verification and explanation are running against the live model."
        }
      >
        <span
          aria-hidden
          className={
            degraded
              ? "inline-block h-1.5 w-1.5 rounded-full"
              : "breathe inline-block h-1.5 w-1.5 rounded-full"
          }
          style={{ background: degraded ? "var(--warn)" : "#4ec9ab" }}
        />
        {degraded ? "Offline · fixtures (degraded)" : "Live models"}
      </span>

      {data?.opik_enabled === false && (
        <span className="text-xs" style={{ color: "var(--bar-soft)" }}>
          traces local
        </span>
      )}

      {/* Which of the two jobs this screen is for. A label, never a login. */}
      <SeatIndicator />

      <nav className="ml-auto flex items-center gap-1 text-sm">
        {NAV.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className="rounded-lg px-3 py-1.5 transition-colors"
            style={({ isActive }) =>
              isActive
                ? { background: "rgba(255,255,255,0.10)", color: "#fff", fontWeight: 600 }
                : { color: "var(--bar-soft)" }
            }
          >
            {label}
          </NavLink>
        ))}

        <span
          aria-hidden
          className="mx-2 h-5 w-px"
          style={{ background: "var(--bar-line)" }}
        />

        <button
          onClick={() => setPresentation((p) => !p)}
          className="rounded-lg px-2.5 py-1.5 text-xs transition-colors"
          style={{ color: "var(--bar-soft)", border: "1px solid var(--bar-line)" }}
          title="Increase type scale and contrast for a large display or screen-share"
        >
          {presentation ? "Normal" : "Present"}
        </button>
        <button
          onClick={() => api.reset().then(() => window.location.reload())}
          className="ml-1 rounded-lg px-2.5 py-1.5 text-xs transition-colors"
          style={{ color: "var(--bar-soft)", border: "1px solid var(--bar-line)" }}
          title="Restore the reference dataset. Traces are kept."
        >
          Reset
        </button>
      </nav>
    </header>
  );
}

export default function App() {
  return (
    <>
      <ReferenceBar />
      <Routes>
        <Route path="/" element={<Console />} />
        <Route path="/policy" element={<Policy />} />
        <Route path="/traces" element={<Traces />} />
      </Routes>
    </>
  );
}

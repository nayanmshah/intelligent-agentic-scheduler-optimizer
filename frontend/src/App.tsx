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
 * Persistent header (FR-104, FR-105, FR-108).
 *
 * A user reading "Thursday the 13th" needs to know the dataset's today is Monday
 * the 10th, or every date on screen looks wrong. The mode indicator is here for the
 * same reason: which path produced this answer is never a guess.
 */
function ReferenceBar() {
  const { data } = useQuery({ queryKey: ["reference"], queryFn: api.reference });
  const [presentation, setPresentation] = useState(false);

  useEffect(() => {
    document.documentElement.dataset.presentation = presentation ? "on" : "off";
  }, [presentation]);

  const now = data?.reference_now
    ? new Date(data.reference_now).toLocaleString("en-US", {
        weekday: "long", day: "numeric", month: "long", year: "numeric",
        hour: "numeric", minute: "2-digit",
      })
    : "…";

  return (
    <header
      className="flex items-center gap-4 border-b px-5 py-2 text-sm"
      style={{ borderColor: "var(--line)", background: "var(--surface)" }}
    >
      <strong className="font-semibold">Reference date:</strong>
      <span>{now}</span>

      <span
        className="rounded px-2 py-0.5 text-xs"
        style={{ background: "var(--page)", color: "var(--ink-soft)" }}
      >
        {data?.network === "offline" ? "Offline · fixtures" : "Live model"}
      </span>
      {data?.opik_enabled === false && (
        <span className="text-xs" style={{ color: "var(--ink-soft)" }}>
          traces local
        </span>
      )}

      {/* Which of the two jobs this screen is for. A label, never a login. */}
      <SeatIndicator />

      <nav className="ml-auto flex items-center gap-3 text-xs">
        {NAV.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) => (isActive ? "font-semibold underline" : "")}
          >
            {label}
          </NavLink>
        ))}
        <button
          onClick={() => setPresentation((p) => !p)}
          className="rounded border px-2 py-0.5"
          style={{ borderColor: "var(--line)" }}
          title="Increase type scale and contrast for a large display or screen-share"
        >
          {presentation ? "Normal" : "Presentation"}
        </button>
        <button
          onClick={() => api.reset().then(() => window.location.reload())}
          className="rounded border px-2 py-0.5"
          style={{ borderColor: "var(--line)" }}
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

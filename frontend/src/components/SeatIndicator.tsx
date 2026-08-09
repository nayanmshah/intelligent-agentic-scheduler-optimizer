import { useLocation } from "react-router-dom";

/**
 * Which seat the current screen is for.
 *
 * The console and the policy panel are two different jobs -- a coordinator executing
 * policy, a manager setting it -- and during a walkthrough that switch is easy to
 * miss when it is only a nav click.
 *
 * **This is a label, not a login.** There is no authentication in v1.0 and this must
 * not imply one: no avatar, no "signed in as", no user menu. Those would suggest an
 * access boundary that does not exist, which is worse than showing nothing. The
 * tooltip says so outright, because someone will ask.
 *
 * The real boundary is a deliberate non-goal, recorded in known-limitations.md §4:
 * any deployment past a single trusted workstation needs real authorization before
 * the policy panel is exposed.
 */
const SEATS: Record<string, { seat: string; does: string }> = {
  "/": {
    seat: "Front desk",
    does: "Takes the request and books. No weight controls on this screen, by design.",
  },
  "/policy": {
    seat: "Practice manager",
    does: "Sets the weights once, for every request. Not a per-call control.",
  },
  "/traces": {
    seat: "Audit",
    does: "Every decision, replayable, with each stage and any fallback that fired.",
  },
};

export function SeatIndicator() {
  const { pathname } = useLocation();
  const entry = SEATS[pathname];
  if (!entry) return null;

  return (
    <span
      className="flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs"
      style={{
        background: "rgba(255,255,255,0.07)",
        border: "1px solid var(--bar-line)",
        color: "var(--bar-soft)",
      }}
      title={`${entry.does}\n\nScreens are separated by role, not by login — there is no authentication in v1.0.`}
    >
      {/* Decorative only: the seat name carries the meaning, so the dot must not be
          the sole signal (NFR-24 -- nothing may depend on colour alone). */}
      <span
        aria-hidden
        className="inline-block h-1.5 w-1.5 rounded-full"
        style={{ background: "#4ec9ab" }}
      />
      <span>
        Seat: <strong className="font-semibold" style={{ color: "var(--bar-ink)" }}>{entry.seat}</strong>
      </span>
    </span>
  );
}

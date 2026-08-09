# Security Review

> Conducted after development completed, against the committed tree. Findings are
> listed with what was done about them — fixed, accepted, or deferred with a reason.
> Nothing here is a checklist recital: each item below was probed against the running
> system rather than reasoned about from the source.

---


## Dictation sends audio to a third party (FR-110)

**Finding.** The console's speech input uses the browser's Web Speech API. In Chromium this
transcribes **server-side at Google**: the microphone stream leaves the machine. No API key or
account is involved, which is precisely the point — the free tier is the tradeoff.

**Assessment for v1.0: accepted, with the boundary named.** The dataset is synthetic, no real
patient is ever dictated, and the feature is off with one flag (`SCHED_VOICE_INPUT=false`). No
audio is recorded, stored or logged by this application at any point — the browser holds the
stream and hands back text, and only the confirmed transcript is ever persisted, as `raw_text`,
already marked PHI and already covered by the existing redaction path.

**What production would require.** Real patient audio is PHI in transit, so a practice deployment
needs local transcription (Whisper-class, on the machine) or a vendor under a BAA. That is a
browser-layer swap: the pipeline receives text either way, so nothing downstream is affected. The
`source` field already distinguishes dictated decisions, so any retrospective review can find them.

**Also note:** the microphone is only ever active while the operator holds the control open — the
button is an explicit toggle with a visible listening state, never an ambient listener.

## Findings fixed

### 1. The request boundary accepted anything — HIGH for correctness, not for exploit

**Found by** driving twelve adversarial inputs through the orchestrator.

An **empty request produced three confident offers.** Every field fell back to a
default — 14-day horizon, `routine`, adult cleaning, any time — and none of that was
surfaced. An operator who fat-fingers Enter on an empty box got a plausible answer to a
question nobody asked. A 24 KB request was also accepted and processed in full.

**Fixed** in two places, deliberately:

- `SubmitRequest` now rejects blank-after-strip text and caps length at 2000
  characters, returning 422.
- The verifier raises `NO_REQUEST_TEXT` independently, because the orchestrator is
  callable directly and the HTTP model is not the only way in.

### 2. The API layer had no tests at all

Everything below the routes was well covered. The boundary itself — where untrusted
text arrives — was not, which is precisely why finding #1 survived to here.

**Fixed:** `tests/requirements/test_s6_api.py`, 13 tests over the real app, covering
input validation, hostile input, response contract, the `/api` 404-vs-SPA-fallback
ordering, and the reference/preflight endpoints.

### 3. Five vulnerable dev dependencies (1 critical, 1 high, 3 moderate)

`vite` (path traversal in optimized-deps `.map` handling), `esbuild` (any website can
issue requests to the dev server and read the response), and the `vitest` chain.

Production dependencies were already clean — `npm audit --omit=dev` reported zero, and
the shipped artifact is a static bundle. But the esbuild issue affects anyone running
`npm run dev`, which is a real developer machine.

**Fixed:** upgraded to `vite@7`, `vitest@3`, `@vitejs/plugin-react@5`. **0
vulnerabilities**; build and tests verified after the upgrade.

Python dependencies were audited in the same pass with `pip-audit` against the
installed environment: **no known vulnerabilities** across all 29 packages. Both scans
are now a single command, `make audit`, so the result is reproducible rather than a
one-off claim in this document.

---

## Verified safe

Each of these was tested, not assumed.

| Surface | Result |
| :------ | :----- |
| **Prompt injection** | *"Ignore all previous instructions…"*, `SYSTEM:` role confusion, and an instruction to return a specific provider all produced normal answers. Extraction output is a typed schema and the ranking is a pure function the model cannot reach, so the worst an injection achieves is the wrong *search* — never an infeasible booking. Asserted in the test suite, not argued. |
| **Path traversal** | The SPA catch-all never joins user input to a path — it returns `index.html` unconditionally. `/assets` is Starlette `StaticFiles`, which guards traversal itself. `cleaning ../../../../etc/passwd` is just text. |
| **Injection into storage** | There is no SQL and no shell. `'; DROP TABLE appointments; --` is a request for a cleaning. |
| **Script injection** | Payloads are stored and echoed as data; React escapes by default and nothing uses `dangerouslySetInnerHTML`. |
| **Malformed input** | Null bytes, bidi overrides, whitespace-only, and 24 KB inputs are all handled without an unhandled exception. |
| **Secret handling** | `ANTHROPIC_API_KEY` is read in `config.py` and used in `client.py` — nowhere else. `describe()` exposes `api_key_present` as a **boolean**; the value never reaches a response, a log, or a trace. `.env` is gitignored and was verified so before the commit. |
| **PHI in observability** | The external (Opik) sink is wrapped in `RedactingSink(PhiRedactor())`; the redactor is derived from `Annotated[..., PHI]` on the domain model rather than a hand-maintained field list, so a new PHI field cannot be silently missed. |
| **Network exposure** | The server binds `127.0.0.1`. One process serves the API and the SPA from the same origin, so there is no CORS policy to get wrong. |

---

## Accepted for v1.0, with reasons

These are deliberate, and each is recorded in
[`known-limitations.md`](known-limitations.md) rather than only here.

**No authentication or authorization.** `/` and `/policy` are separate routes, not
separate roles, and every mutating endpoint — book, hold, reset, set weights — is
unauthenticated. At single-workstation scale this adds no decision quality. **Any
deployment beyond a single trusted workstation must add real authorization before the
policy panel is exposed**: a front-desk user who can reach `/policy` and move the
weights is exactly the consistency destruction this product exists to eliminate.

**The local trace store is not redacted.** It is the byte-identical replay substrate
and lives in memory on one machine (AR-06). This reasoning is v1.0-specific and
**inverts in production**, where the local store is a database and `raw_text` is PHI at
rest.

**`/api/docs` and `/api/openapi.json` are exposed.** Self-documenting is a feature for
a local tool. In a deployed environment they should be disabled or gated — they
enumerate every route for anyone who can reach the port.

**Urgency is patient-asserted.** Saying "this is an emergency" sets
`urgency=emergency`, which unlocks reserved emergency-hold slots (FR-036). This is
triage working as designed with a human in the loop: the operator types the patient's
words, and the interpretation strip shows the resulting urgency and the span it came
from. It is a policy question for the practice, not a software control, and it is
visible rather than silent.

---

## Not covered

- **Dependency provenance.** Versions are pinned via `uv.lock` and
  `package-lock.json`, but there is no signature verification or SBOM.
- **Rate limiting.** Single-operator scope; the 2000-character cap is the only input
  bound.
- **Multi-seat authorization.** Blocked on there being seats — see limitation §7.
- **Continuous scanning.** `make audit` runs both audits on demand, but nothing runs
  them on a schedule. A lockfile that was clean today is the thing most likely to stop
  being clean without anyone touching the code.

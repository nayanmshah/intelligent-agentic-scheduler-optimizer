/**
 * FR-110. The behaviour worth pinning is not "speech works" — that is the browser's
 * job — but the two rules that keep provenance honest when it does:
 *
 *   1. a transcript is *appended to the box*, never submitted;
 *   2. an absent API produces no control at all, rather than one that does nothing.
 */
import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useSpeech } from "@/lib/useSpeech";

type Handler = ((e: unknown) => void) | null;

/** The slice of `webkitSpeechRecognition` the hook actually touches. */
class FakeRecognition {
  static last: FakeRecognition | null = null;
  lang = "";
  continuous = false;
  interimResults = false;
  maxAlternatives = 0;
  started = false;
  onresult: Handler = null;
  onerror: Handler = null;
  onend: (() => void) | null = null;

  constructor() {
    FakeRecognition.last = this;
  }
  start() {
    this.started = true;
  }
  stop() {
    this.started = false;
    this.onend?.();
  }
  abort() {
    this.started = false;
  }

  /** Drive the callback the way Chrome does: interim results, then a final one. */
  emit(transcript: string, isFinal: boolean) {
    const result = Object.assign([{ transcript, confidence: 0.9 }], { isFinal });
    this.onresult?.({ resultIndex: 0, results: [result] });
  }
}

const w = window as unknown as { webkitSpeechRecognition?: unknown };

beforeEach(() => {
  FakeRecognition.last = null;
  w.webkitSpeechRecognition = FakeRecognition;
});
afterEach(() => {
  delete w.webkitSpeechRecognition;
  vi.restoreAllMocks();
});

describe("useSpeech", () => {
  it("reports unsupported when the browser has no speech API", () => {
    delete w.webkitSpeechRecognition;
    const { result } = renderHook(() => useSpeech(() => {}));
    expect(result.current.supported).toBe(false);
    // The console renders no button in this state: a control that cannot work is
    // worse than an absent one, because it teaches the operator to distrust the bar.
  });

  it("reports supported and configures continuous, interim recognition", () => {
    const { result } = renderHook(() => useSpeech(() => {}));
    expect(result.current.supported).toBe(true);
    const rec = FakeRecognition.last!;
    // Continuous, because a patient's sentence has pauses in it; interim, because
    // silence for four seconds reads as a broken microphone.
    expect(rec.continuous).toBe(true);
    expect(rec.interimResults).toBe(true);
  });

  it("hands settled phrases to the caller and never submits them itself", () => {
    const onFinal = vi.fn();
    const { result } = renderHook(() => useSpeech(onFinal));
    act(() => result.current.start());
    act(() => FakeRecognition.last!.emit("next Thursday after three", true));

    expect(onFinal).toHaveBeenCalledWith("next Thursday after three");
    // The hook's whole contract: it returns text. Anything that looked like a
    // submit here would put an unconfirmed transcript into the audit trail.
    expect(Object.keys(result.current)).not.toContain("submit");
  });

  it("shows interim words without ever handing them over", () => {
    const onFinal = vi.fn();
    const { result } = renderHook(() => useSpeech(onFinal));
    act(() => result.current.start());
    act(() => FakeRecognition.last!.emit("next Tuesd", false));

    expect(result.current.interim).toBe("next Tuesd");
    expect(onFinal).not.toHaveBeenCalled(); // half-heard words are not a request
  });

  it("explains a blocked microphone in words an operator can act on", () => {
    const { result } = renderHook(() => useSpeech(() => {}));
    act(() => result.current.start());
    act(() => FakeRecognition.last!.onerror?.({ error: "not-allowed" }));

    expect(result.current.error).toMatch(/microphone blocked/i);
    expect(result.current.error).toMatch(/type/i); // the way out is always named
    expect(result.current.listening).toBe(false);
  });

  it("stays silent about aborts, which are what stop() raises", () => {
    const { result } = renderHook(() => useSpeech(() => {}));
    act(() => result.current.start());
    act(() => FakeRecognition.last!.onerror?.({ error: "aborted" }));
    expect(result.current.error).toBeNull();
  });

  it("survives a caller that changes on every keystroke", () => {
    // The console's callback closes over `text`, so it is a new function each
    // render. Rebuilding the recogniser on that would drop audio mid-sentence.
    const first = vi.fn();
    const { result, rerender } = renderHook(({ cb }) => useSpeech(cb), {
      initialProps: { cb: first },
    });
    const original = FakeRecognition.last;
    act(() => result.current.start());

    const second = vi.fn();
    rerender({ cb: second });
    expect(FakeRecognition.last).toBe(original); // not rebuilt

    act(() => FakeRecognition.last!.emit("prefer Sarah", true));
    expect(second).toHaveBeenCalledWith("prefer Sarah"); // and the new sink is used
    expect(first).not.toHaveBeenCalled();
  });
});

/**
 * Dictation, as a front door to the same text box (FR-110).
 *
 * The load-bearing decision is what this hook *does not* do: it never submits. It
 * writes a transcript into the field the operator is already looking at, and they
 * press enter. That keeps FR-003 true — every extracted field points at a verbatim
 * span of `request_text`, and `request_text` is exactly what a human confirmed. Let
 * speech submit itself and the provenance chips start quoting the transcriber rather
 * than the patient, and a misheard "Tuesday" becomes ground truth silently.
 *
 * The browser API is `webkitSpeechRecognition` in Chromium and `SpeechRecognition`
 * in the standard; neither exists in Firefox. Support is therefore a runtime fact,
 * not a build-time one, which is why `supported` is state rather than a constant.
 */
import { useCallback, useEffect, useRef, useState } from "react";

/** The slice of the Web Speech API this uses. The DOM lib does not ship it. */
type SpeechRecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((e: SpeechRecognitionEventLike) => void) | null;
  onerror: ((e: { error?: string }) => void) | null;
  onend: (() => void) | null;
};

type SpeechRecognitionEventLike = {
  resultIndex: number;
  results: ArrayLike<
    ArrayLike<{ transcript: string; confidence: number }> & { isFinal: boolean }
  >;
};

type Ctor = new () => SpeechRecognitionLike;

function constructor(): Ctor | null {
  const w = window as unknown as {
    SpeechRecognition?: Ctor;
    webkitSpeechRecognition?: Ctor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export type SpeechState = {
  /** False in Firefox, and in any browser where the API was removed or blocked. */
  supported: boolean;
  listening: boolean;
  /** Words heard but not yet settled. Shown greyed, never submitted. */
  interim: string;
  /** Set when the browser refuses: denied microphone, no speech, network. */
  error: string | null;
  start: () => void;
  stop: () => void;
};

/**
 * @param onFinal called with each settled phrase, to be appended to the box.
 */
export function useSpeech(onFinal: (text: string) => void): SpeechState {
  const [supported, setSupported] = useState(false);
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<SpeechRecognitionLike | null>(null);

  // `onFinal` closes over the current text, so it changes every keystroke. Keeping
  // it in a ref means the recogniser is built once instead of being torn down and
  // rebuilt mid-sentence — which silently drops audio.
  const sink = useRef(onFinal);
  useEffect(() => {
    sink.current = onFinal;
  }, [onFinal]);

  useEffect(() => {
    const Ctor = constructor();
    if (!Ctor) return;
    setSupported(true);

    const rec = new Ctor();
    rec.lang = "en-US";
    rec.continuous = true; // a patient's sentence has pauses in it
    rec.interimResults = true;
    rec.maxAlternatives = 1;

    rec.onresult = (e) => {
      let settled = "";
      let pending = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const result = e.results[i]!;
        const text = result[0]!.transcript;
        if (result.isFinal) settled += text;
        else pending += text;
      }
      setInterim(pending);
      if (settled.trim()) {
        setInterim("");
        sink.current(settled.trim());
      }
    };

    rec.onerror = (e) => {
      // "aborted" is what stop() raises; it is not a failure worth showing.
      if (e.error === "aborted") return;
      setError(
        e.error === "not-allowed"
          ? "Microphone blocked — allow access in the browser, or just type."
          : e.error === "no-speech"
            ? "Nothing heard."
            : "Dictation stopped.",
      );
      setListening(false);
    };

    rec.onend = () => {
      setListening(false);
      setInterim("");
    };

    ref.current = rec;
    return () => {
      rec.onresult = rec.onerror = rec.onend = null;
      rec.abort();
      ref.current = null;
    };
  }, []);

  const start = useCallback(() => {
    if (!ref.current || listening) return;
    setError(null);
    setInterim("");
    try {
      ref.current.start();
      setListening(true);
    } catch {
      // start() throws if it is already running; the state is what we wanted anyway.
      setListening(true);
    }
  }, [listening]);

  const stop = useCallback(() => {
    ref.current?.stop();
    setListening(false);
  }, []);

  return { supported, listening, interim, error, start, stop };
}

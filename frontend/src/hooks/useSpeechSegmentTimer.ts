import { useEffect, useState } from 'react';

export function voiceUtteranceCapMs(): number {
  const raw = import.meta.env.VITE_VOICE_MAX_UTTERANCE_MS as string | undefined;
  const n = raw ? Number.parseInt(raw, 10) : 60_000;
  return Number.isFinite(n) && n > 0 ? n : 60_000;
}

export type SpeechSegmentTimer = {
  /** Wall time since mic was unmuted (ms). */
  unmutedMs: number;
  capMs: number;
  warn: boolean;
  overCap: boolean;
};

/** Counts how long the mic has been open (unmuted), not VAD speech segments. */
export function useSpeechSegmentTimer(micHot: boolean): SpeechSegmentTimer {
  const capMs = voiceUtteranceCapMs();
  const [unmutedMs, setUnmutedMs] = useState(0);

  useEffect(() => {
    if (!micHot) {
      setUnmutedMs(0);
      return;
    }
    const started = performance.now();
    const tick = () => setUnmutedMs(Math.floor(performance.now() - started));
    tick();
    const id = window.setInterval(tick, 100);
    return () => window.clearInterval(id);
  }, [micHot]);

  const warn = unmutedMs >= capMs * 0.85;
  const overCap = unmutedMs >= capMs;

  return { unmutedMs, capMs, warn, overCap };
}

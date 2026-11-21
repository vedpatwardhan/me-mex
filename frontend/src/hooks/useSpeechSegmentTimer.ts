import { Room, Track } from 'livekit-client';
import { useEffect, useRef, useState } from 'react';

const SPEECH_RMS = 0.016;
const SILENCE_RESET_MS = 650;

export function voiceUtteranceCapMs(): number {
  const raw = import.meta.env.VITE_VOICE_MAX_UTTERANCE_MS as string | undefined;
  const n = raw ? Number.parseInt(raw, 10) : 60_000;
  return Number.isFinite(n) && n > 0 ? n : 60_000;
}

export type SpeechSegmentTimer = {
  /** Continuous speech in the current VAD segment (ms). */
  segmentMs: number;
  /** Mic level suggests the user is speaking right now. */
  speaking: boolean;
  capMs: number;
  /** ≥85% of cap — nudge before hard clip. */
  warn: boolean;
  /** At or over worker max_buffered_speech — mute & continue. */
  overCap: boolean;
};

/**
 * Approximates Silero segment length from local mic RMS while unmuted.
 * Resets after ~650ms silence (same idea as worker end-of-speech).
 */
export function useSpeechSegmentTimer(
  room: Room | null,
  micHot: boolean,
): SpeechSegmentTimer {
  const capMs = voiceUtteranceCapMs();
  const [segmentMs, setSegmentMs] = useState(0);
  const [speaking, setSpeaking] = useState(false);
  const rafRef = useRef<number | null>(null);
  const audioRef = useRef<{
    ctx: AudioContext;
    analyser: AnalyserNode;
    source: MediaStreamAudioSourceNode;
  } | null>(null);
  const segmentMsRef = useRef(0);
  const lastSpeechAtRef = useRef(0);
  const lastTickRef = useRef(0);

  useEffect(() => {
    if (!micHot || !room) {
      segmentMsRef.current = 0;
      setSegmentMs(0);
      setSpeaking(false);
      return;
    }

    const pub = room.localParticipant.getTrackPublication(Track.Source.Microphone);
    const track = pub?.track?.mediaStreamTrack;
    if (!track) {
      return;
    }

    const ctx = new AudioContext();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
    const source = ctx.createMediaStreamSource(new MediaStream([track]));
    source.connect(analyser);
    audioRef.current = { ctx, analyser, source };
    lastTickRef.current = performance.now();
    lastSpeechAtRef.current = 0;

    const buf = new Float32Array(analyser.fftSize);

    const tick = () => {
      analyser.getFloatTimeDomainData(buf);
      let sum = 0;
      for (let i = 0; i < buf.length; i += 1) sum += buf[i] * buf[i];
      const rms = Math.sqrt(sum / buf.length);
      const now = performance.now();
      const dt = now - lastTickRef.current;
      lastTickRef.current = now;

      const isSpeech = rms >= SPEECH_RMS;
      setSpeaking(isSpeech);
      if (isSpeech) {
        lastSpeechAtRef.current = now;
        segmentMsRef.current += dt;
      } else if (
        lastSpeechAtRef.current > 0 &&
        now - lastSpeechAtRef.current >= SILENCE_RESET_MS
      ) {
        segmentMsRef.current = 0;
        lastSpeechAtRef.current = 0;
      }
      setSegmentMs(Math.floor(segmentMsRef.current));
      rafRef.current = requestAnimationFrame(tick);
    };

    void ctx.resume();
    rafRef.current = requestAnimationFrame(tick);

    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      source.disconnect();
      void ctx.close();
      audioRef.current = null;
      segmentMsRef.current = 0;
      setSegmentMs(0);
      setSpeaking(false);
    };
  }, [room, micHot]);

  const warn = segmentMs >= capMs * 0.85;
  const overCap = segmentMs >= capMs;

  return { segmentMs, speaking, capMs, warn, overCap };
}

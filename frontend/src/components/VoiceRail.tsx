import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Mic, MicOff, PhoneOff, Radio } from 'lucide-react';

import { SpeechSegmentIndicator } from './SpeechSegmentIndicator';
import { useSpeechSegmentTimer } from '../hooks/useSpeechSegmentTimer';
import type { VoiceContext } from '../services/voiceSession';
import { VoiceSession } from '../services/voiceSession';
import type { VoiceSessionState } from '../services/livekitService';
import { parseCustomFields } from '../utils/dockUtils';

type Props = {
  projectId?: string;
  selectedNodeId?: string | null;
  projectIntroduction?: string;
  onMuteToggle?: (muted: boolean) => void;
  onContext?: (ctx: VoiceContext) => void;
  onDockStreamEvent?: (ev: Record<string, unknown>) => void;
  onVoiceSession?: (session: VoiceSession | null) => void;
};

function statusMeta(
  state: VoiceSessionState,
  live: boolean,
  connected: boolean,
): { label: string; detail: string; dot: string; ring: string } {
  if (!connected) {
    return {
      label: 'Offline',
      detail: 'Start a session to use the mic',
      dot: 'bg-slate-500',
      ring: 'border-slate-600/60 bg-slate-800/40',
    };
  }
  if (state === 'Thinking') {
    return {
      label: 'Connecting',
      detail: 'Joining LiveKit room…',
      dot: 'bg-sky-400 animate-pulse',
      ring: 'border-sky-500/40 bg-sky-500/10',
    };
  }
  if (state === 'Speaking') {
    return {
      label: 'Speaking',
      detail: 'Playing assistant audio',
      dot: 'bg-violet-400',
      ring: 'border-violet-500/40 bg-violet-500/10',
    };
  }
  if (state === 'Awaiting approval') {
    return {
      label: 'Approval',
      detail: 'Confirm a pending write',
      dot: 'bg-amber-400',
      ring: 'border-amber-500/40 bg-amber-500/10',
    };
  }
  if (live) {
    return {
      label: 'Listening',
      detail: 'Mic open — mute when done to send',
      dot: 'bg-emerald-400',
      ring: 'border-emerald-500/40 bg-emerald-500/10',
    };
  }
  return {
    label: 'Muted',
    detail: 'Session active, mic paused',
    dot: 'bg-amber-500',
    ring: 'border-amber-500/30 bg-amber-500/10',
  };
}

export const VoiceRail: React.FC<Props> = ({
  projectId,
  selectedNodeId,
  projectIntroduction,
  onMuteToggle,
  onContext,
  onDockStreamEvent,
  onVoiceSession,
}) => {
  const [muted, setMuted] = useState(true);
  const [state, setState] = useState<VoiceSessionState>('Muted');
  const [customFields, setCustomFields] = useState('arxiv_id=\nroot_id=');
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const sessionRef = useRef<VoiceSession | null>(null);
  const [connecting, setConnecting] = useState(false);
  const setVoiceStateRef = useRef(setState);
  useEffect(() => {
    setVoiceStateRef.current = setState;
  });

  const threadId = useMemo(
    () => `voice-${projectId || 'default'}`,
    [projectId],
  );

  const ensureSession = () => {
    if (!sessionRef.current) {
      sessionRef.current = new VoiceSession(
        (s) => setVoiceStateRef.current(s),
        (ev) => onDockStreamEvent?.(ev),
      );
      onVoiceSession?.(sessionRef.current);
    } else if (onDockStreamEvent) {
      sessionRef.current.setDockEventHandler(onDockStreamEvent);
    }
    return sessionRef.current;
  };

  useEffect(() => {
    sessionRef.current?.setDockEventHandler(onDockStreamEvent);
  }, [onDockStreamEvent]);

  const contextForWorker = (micMuted = muted): VoiceContext => ({
    active_project_id: projectId || '',
    muted: micMuted,
    custom_fields: parseCustomFields(customFields),
    selected_node_ids: selectedNodeId ? [selectedNodeId] : [],
    thread_id: threadId,
  });

  useEffect(() => {
    const session = sessionRef.current;
    if (!session?.isReady() || state === 'Thinking') return;
    session.publishContextFireAndForget(contextForWorker(muted));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- republish project/selection/mic
  }, [projectId, selectedNodeId, threadId, muted]);

  const roomReady = sessionRef.current?.isReady() ?? false;
  const connected =
    roomReady &&
    (state === 'Listening' ||
      state === 'Speaking' ||
      state === 'Awaiting approval' ||
      (muted && state === 'Muted'));
  const live = connected && !muted && state === 'Listening';
  const status = statusMeta(state, live, connected);
  const speechTimer = useSpeechSegmentTimer(live);

  const startSession = async () => {
    if (connecting) return;
    setConnecting(true);
    const session = ensureSession();
    const ctx = contextForWorker(false);
    onContext?.(ctx);
    setVoiceError(null);
    try {
      setState('Thinking');
      setMuted(false);
      if (!session.isReady()) {
        await session.connect(`user-${projectId || 'me'}-${Date.now()}`);
      }
      if (!session.isReady()) {
        throw new Error('Could not join LiveKit room');
      }
      const scopeCtx = !projectIntroduction?.trim()
        ? {
            ...ctx,
            custom_fields: { ...ctx.custom_fields, force_project_scope: '1' },
          }
        : ctx;
      session.setLiveContext(scopeCtx);
      setState('Listening');
      setMuted(false);
      onMuteToggle?.(false);
      session.publishContextFireAndForget({ ...scopeCtx, muted: false });
      await session.setMicrophoneEnabled(true);
    } catch (err) {
      const raw = err instanceof Error ? err.message : 'Voice connection failed';
      const message =
        /permission denied/i.test(raw) || /NotAllowedError/i.test(raw)
          ? 'Microphone blocked. On this Mac use http://127.0.0.1:3000 and allow mic when prompted. Phone browsers need HTTPS (or use the Mac browser for voice). Reset in Chrome: Site settings → Microphone.'
          : raw;
      setVoiceError(message);
      setState('Muted');
      setMuted(true);
      onMuteToggle?.(true);
      void session.disconnect();
    } finally {
      setConnecting(false);
    }
  };

  const setMicMuted = (micMuted: boolean) => {
    const session = ensureSession();
    if (!session.isReady()) return;
    const ctx = contextForWorker(micMuted);
    onContext?.(ctx);
    setVoiceError(null);
    setMuted(micMuted);
    setState(micMuted ? 'Muted' : 'Listening');
    onMuteToggle?.(micMuted);
    void session.applyMicMuted(micMuted, ctx).catch((err) => {
      const message = err instanceof Error ? err.message : 'Could not update mic';
      setVoiceError(message);
    });
  };

  const endSession = () => {
    const session = sessionRef.current;
    setVoiceError(null);
    sessionRef.current = null;
    onVoiceSession?.(null);
    setState('Muted');
    setMuted(true);
    onMuteToggle?.(true);
    if (session) void session.disconnect();
  };

  return (
    <aside className="flex w-[17.5rem] shrink-0 flex-col gap-4 border-r border-white/10 bg-[#0c1018]/95 px-4 py-5 overflow-y-auto">
      <header className="space-y-1">
        <div className="flex items-center gap-2 text-slate-200">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-cyan-500/30 bg-cyan-500/10">
            <Radio className="h-4 w-4 text-cyan-400" />
          </span>
          <div>
            <h2 className="text-sm font-semibold tracking-tight">Voice rail</h2>
            <p className="text-[11px] text-slate-500">LiveKit · same thread as graph</p>
          </div>
        </div>
      </header>

      <div className="glass-panel rounded-xl px-3 py-2.5">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          Active project
        </p>
        <p className="mt-1 truncate text-sm font-medium text-emerald-300/90">
          {projectId || '—'}
        </p>
        {selectedNodeId ? (
          <p className="mt-1 truncate text-[11px] text-slate-500" title={selectedNodeId}>
            Node: {selectedNodeId}
          </p>
        ) : null}
      </div>

      <div className={`rounded-xl border px-3 py-2.5 ${status.ring}`}>
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 shrink-0 rounded-full ${status.dot}`} />
          <span className="text-sm font-medium text-slate-100">{status.label}</span>
        </div>
        <p className="mt-1 text-xs leading-relaxed text-slate-400">{status.detail}</p>
      </div>

      {connected && !muted ? <SpeechSegmentIndicator timer={speechTimer} visible /> : null}

      <MotionButtons
        connected={connected}
        connecting={connecting}
        live={live}
        state={state}
        onStart={() => void startSession()}
        onToggleMute={() => setMicMuted(!muted)}
        onEnd={endSession}
      />

      {connected && muted ? (
        <button
          type="button"
          className="w-full rounded-lg border border-slate-600/80 bg-slate-800/50 px-3 py-2 text-left text-xs text-slate-300 transition hover:border-slate-500 hover:bg-slate-800"
          onClick={() => {
            const s = ensureSession();
            if (s.isReady()) void s.sendAgentTurn('', contextForWorker(true));
          }}
        >
          Send turn with custom fields only
        </button>
      ) : null}

      {!projectIntroduction?.trim() && connected ? (
        <p className="rounded-lg border border-cyan-500/25 bg-cyan-500/10 px-3 py-2 text-xs leading-relaxed text-cyan-200/90">
          Unmute once to capture project scope (P1).
        </p>
      ) : null}

      {voiceError ? (
        <div
          className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs leading-relaxed text-rose-300"
          role="alert"
        >
          {voiceError}
        </div>
      ) : null}

      <section className="glass-panel mt-auto flex flex-col gap-2 rounded-xl p-3">
        <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          Custom fields
        </label>
        <p className="text-[11px] leading-snug text-slate-500">
          Key=value per line. Overrides conflicting STT on each turn.
        </p>
        <textarea
          className="min-h-[7.5rem] w-full resize-y rounded-lg border border-slate-700/80 bg-[#0a0e16] p-2.5 font-mono text-xs leading-relaxed text-slate-200 placeholder:text-slate-600 focus:border-cyan-500/50 focus:outline-none focus:ring-1 focus:ring-cyan-500/30"
          value={customFields}
          onChange={(e) => {
            setCustomFields(e.target.value);
            const ctx = contextForWorker(muted);
            onContext?.(ctx);
            const s = ensureSession();
            if (s.isReady() && state !== 'Thinking') s.publishContextFireAndForget(ctx);
          }}
          spellCheck={false}
        />
      </section>
    </aside>
  );
};

type MotionProps = {
  connected: boolean;
  connecting: boolean;
  live: boolean;
  state: VoiceSessionState;
  onStart: () => void;
  onToggleMute: () => void;
  onEnd: () => void;
};

function MotionButtons({
  connected,
  connecting,
  live,
  state,
  onStart,
  onToggleMute,
  onEnd,
}: MotionProps) {
  if (!connected) {
    return (
      <button
        type="button"
        disabled={state === 'Thinking' || connecting}
        onClick={onStart}
        className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-900/30 transition hover:from-indigo-500 hover:to-violet-500 disabled:opacity-60"
      >
        <Mic className="h-4 w-4" />
        {state === 'Thinking' || connecting ? 'Connecting…' : 'Start voice session'}
      </button>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        disabled={state === 'Thinking'}
        onClick={onToggleMute}
        className={`flex w-full items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold text-white transition disabled:opacity-60 ${
          live
            ? 'bg-emerald-600 hover:bg-emerald-500 shadow-emerald-900/20 shadow-md'
            : 'bg-amber-600 hover:bg-amber-500 shadow-md shadow-amber-900/20'
        }`}
      >
        {live ? <Mic className="h-4 w-4" /> : <MicOff className="h-4 w-4" />}
        {live ? 'Mute microphone' : 'Unmute microphone'}
      </button>
      <button
        type="button"
        onClick={onEnd}
        className="flex w-full items-center justify-center gap-2 rounded-xl border border-slate-600/80 bg-slate-800/40 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-slate-500 hover:bg-slate-800/80"
      >
        <PhoneOff className="h-4 w-4 text-slate-400" />
        End session
      </button>
    </div>
  );
}

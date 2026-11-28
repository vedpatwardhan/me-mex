import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { LoaderCircle, Mic, MicOff, PhoneOff, Radio } from 'lucide-react';

import { SpeechSegmentIndicator } from './SpeechSegmentIndicator';
import { useSpeechSegmentTimer } from '../hooks/useSpeechSegmentTimer';
import type { DockTurnContext, VoiceSessionState } from '../services/dockTurnTypes';
import {
  abortVoiceTurn,
  MicCaptureSession,
  streamVoiceConversation,
  subscribeSessionEvents,
  transcribeAudio,
  voiceContextToJson,
} from '../services/dockTurnClient';
import {
  customFieldsForContext,
  INITIAL_CUSTOM_FIELDS,
  mergeOneShotCustomFields,
  parseCustomFields,
} from '../utils/dockUtils';
import { flattenDockEvents } from '../utils/dockStreamReducer';

type Props = {
  projectId?: string;
  selectedNodeId?: string | null;
  projectIntroduction?: string;
  onMuteToggle?: (muted: boolean) => void;
  onContext?: (ctx: DockTurnContext) => void;
  onDockStreamEvent?: (ev: Record<string, unknown>) => void;
};

function statusMeta(
  state: VoiceSessionState,
  live: boolean,
  connected: boolean,
  sessionConnecting: boolean,
): { label: string; detail: string; dot: string; ring: string } {
  if (!connected) {
    return {
      label: 'Offline',
      detail: 'Start a session to use the mic',
      dot: 'bg-slate-500',
      ring: 'border-slate-600/60 bg-slate-800/40',
    };
  }
  if (state === 'Thinking' && sessionConnecting) {
    return {
      label: 'Starting',
      detail: 'Requesting microphone…',
      dot: 'bg-sky-400 animate-pulse',
      ring: 'border-sky-500/40 bg-sky-500/10',
    };
  }
  if (state === 'Processing') {
    return {
      label: 'Processing',
      detail: 'Assistant is working on your turn…',
      dot: 'bg-sky-400 animate-pulse',
      ring: 'border-sky-500/40 bg-sky-500/10',
    };
  }
  if (state === 'Streaming') {
    return {
      label: 'Streaming',
      detail: 'Assistant reply streaming to the dock…',
      dot: 'bg-violet-400 animate-pulse',
      ring: 'border-violet-500/40 bg-violet-500/10',
    };
  }
  if (state === 'Transcribing') {
    return {
      label: 'Transcribing',
      detail: 'Turning your speech into text…',
      dot: 'bg-cyan-400 animate-pulse',
      ring: 'border-cyan-500/40 bg-cyan-500/10',
    };
  }
  if (state === 'Reviewing') {
    return {
      label: 'Review',
      detail: 'Edit transcript, then send or discard',
      dot: 'bg-cyan-400',
      ring: 'border-cyan-500/40 bg-cyan-500/10',
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

export const CaptureRail: React.FC<Props> = ({
  projectId,
  selectedNodeId,
  projectIntroduction,
  onMuteToggle,
  onContext,
  onDockStreamEvent,
}) => {
  const [muted, setMuted] = useState(true);
  const [state, setState] = useState<VoiceSessionState>('Muted');
  const [customFields, setCustomFields] = useState(INITIAL_CUSTOM_FIELDS);
  const customFieldsRef = useRef(customFields);
  customFieldsRef.current = customFields;
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [sttDraft, setSttDraft] = useState<string | null>(null);
  const [sessionActive, setSessionActive] = useState(false);
  const micRef = useRef<MicCaptureSession | null>(null);
  const sessionEventsRef = useRef<ReturnType<typeof subscribeSessionEvents> | null>(null);
  const turnAbortRef = useRef<AbortController | null>(null);
  const activeTurnIdRef = useRef<string | null>(null);
  const pendingTurnFieldsRef = useRef<Record<string, string> | null>(null);
  const mutedRef = useRef(muted);
  mutedRef.current = muted;
  const resetFieldsAfterTurnRef = useRef(false);
  const submittedTurnStartedRef = useRef(false);
  const [connecting, setConnecting] = useState(false);
  const setVoiceStateRef = useRef(setState);
  useEffect(() => {
    setVoiceStateRef.current = setState;
  });

  const threadId = useMemo(
    () => `voice-${projectId || 'default'}`,
    [projectId],
  );

  const contextForWorker = useCallback((micMuted = muted): DockTurnContext => {
    return {
      active_project_id: projectId || '',
      muted: micMuted,
      custom_fields: customFieldsForContext(
        pendingTurnFieldsRef.current,
        customFields,
        micMuted,
      ),
      selected_node_ids: selectedNodeId ? [selectedNodeId] : [],
      thread_id: threadId,
    };
  }, [customFields, muted, projectId, selectedNodeId, threadId]);

  const commitOneShotCustomFields = useCallback(() => {
    pendingTurnFieldsRef.current = mergeOneShotCustomFields(
      pendingTurnFieldsRef.current,
      customFieldsRef.current,
    );
    setCustomFields(INITIAL_CUSTOM_FIELDS);
    resetFieldsAfterTurnRef.current = true;
  }, []);

  const contextWithCommittedFields = useCallback(
    (micMuted: boolean): DockTurnContext => ({
      active_project_id: projectId || '',
      muted: micMuted,
      custom_fields: customFieldsForContext(pendingTurnFieldsRef.current, '', true),
      selected_node_ids: selectedNodeId ? [selectedNodeId] : [],
      thread_id: threadId,
    }),
    [projectId, selectedNodeId, threadId],
  );

  const emitDock = useCallback(
    (ev: Record<string, unknown>) => {
      onDockStreamEvent?.(ev);
    },
    [onDockStreamEvent],
  );

  const handleDockStreamEvent = useCallback(
    (ev: Record<string, unknown>) => {
      emitDock(ev);
      for (const event of flattenDockEvents(ev)) {
        if (event.type === 'turn_aborted') {
          setVoiceStateRef.current((current) =>
            current === 'Processing' || current === 'Streaming' ? 'Reviewing' : 'Muted',
          );
          continue;
        }
        if (event.type === 'turn_start') {
          submittedTurnStartedRef.current = true;
          if (!resetFieldsAfterTurnRef.current) {
            pendingTurnFieldsRef.current = mergeOneShotCustomFields(
              pendingTurnFieldsRef.current,
              customFieldsRef.current,
            );
            setCustomFields(INITIAL_CUSTOM_FIELDS);
            resetFieldsAfterTurnRef.current = true;
            onContext?.(contextForWorker(mutedRef.current));
          }
          setVoiceStateRef.current('Processing');
          continue;
        }
        if (event.type === 'token') {
          setVoiceStateRef.current((current) =>
            current === 'Processing' ? 'Streaming' : current,
          );
          continue;
        }
        if (event.type === 'turn_end') {
          setVoiceStateRef.current((current) => {
            if (current === 'Processing' || current === 'Streaming') {
              return mutedRef.current ? 'Muted' : 'Listening';
            }
            return current;
          });
          const flushCompleted =
            resetFieldsAfterTurnRef.current && submittedTurnStartedRef.current;
          submittedTurnStartedRef.current = false;
          if (flushCompleted) {
            resetFieldsAfterTurnRef.current = false;
            pendingTurnFieldsRef.current = null;
            onContext?.(contextForWorker(muted));
          }
          turnAbortRef.current = null;
          activeTurnIdRef.current = null;
          continue;
        }
        if (event.type === 'awaiting_approval') {
          setVoiceStateRef.current('Awaiting approval');
        }
      }
    },
    [emitDock, onContext, muted, contextForWorker],
  );

  const ensureSessionEvents = useCallback(() => {
    if (!projectId || sessionEventsRef.current) return;
    sessionEventsRef.current = subscribeSessionEvents(projectId, threadId, (ev) => {
      handleDockStreamEvent(ev);
    });
  }, [projectId, threadId, handleDockStreamEvent]);

  const runSttOnBlob = useCallback(
    async (blob: Blob) => {
      if (blob.size < 400) {
        setVoiceError('No speech detected. Unmute and try again.');
        setVoiceStateRef.current('Muted');
        return;
      }
      emitDock({ type: 'stt_pending' });
      setVoiceStateRef.current('Transcribing');
      try {
        const { text } = await transcribeAudio(blob);
        if (!text) {
          emitDock({ type: 'stt_failed', reason: 'no_speech' });
          setVoiceError('No speech detected. Unmute and try again.');
          setVoiceStateRef.current('Muted');
          return;
        }
        setSttDraft(text);
        setVoiceError(null);
        setVoiceStateRef.current('Reviewing');
        setMuted(true);
      } catch (err) {
        const raw = err instanceof Error ? err.message : 'stt_error';
        const reason = raw === 'speech_disabled' ? 'speech_disabled' : 'stt_error';
        emitDock({ type: 'stt_failed', reason });
        const message =
          reason === 'speech_disabled'
            ? 'Speech service is not configured (Colab URL).'
            : 'Transcription failed. Check backend / Colab and try again.';
        setVoiceError(message);
        setVoiceStateRef.current('Muted');
      }
    },
    [emitDock],
  );

  const sendReviewedTurn = useCallback(
    async (text: string) => {
      commitOneShotCustomFields();
      const ctx = contextWithCommittedFields(true);
      onContext?.(ctx);
      const contextJson = voiceContextToJson(ctx);
      if (!projectIntroduction?.trim()) {
        contextJson.force_project_scope = '1';
      }
      const controller = new AbortController();
      turnAbortRef.current = controller;
      setSttDraft(null);
      setState('Processing');
      setMuted(true);
      try {
        const { turnId } = await streamVoiceConversation({
          text,
          threadId,
          contextJson,
          onEvent: handleDockStreamEvent,
          signal: controller.signal,
        });
        activeTurnIdRef.current = turnId;
      } catch (err) {
        if (controller.signal.aborted) return;
        const message = err instanceof Error ? err.message : 'Turn failed';
        setVoiceError(message);
        setState('Muted');
      }
    },
    [
      commitOneShotCustomFields,
      contextWithCommittedFields,
      onContext,
      projectIntroduction,
      threadId,
      handleDockStreamEvent,
    ],
  );

  useEffect(() => {
    return () => {
      sessionEventsRef.current?.stop();
      micRef.current?.dispose();
      turnAbortRef.current?.abort();
    };
  }, []);

  const connected = sessionActive;
  const live = connected && !muted && state === 'Listening';
  const status = statusMeta(state, live, connected, connecting);
  const speechTimer = useSpeechSegmentTimer(live);

  const startSession = async () => {
    if (connecting) return;
    setConnecting(true);
    setVoiceError(null);
    try {
      setState('Thinking');
      ensureSessionEvents();
      micRef.current = new MicCaptureSession();
      await micRef.current.start();
      setSessionActive(true);
      setState('Listening');
      setMuted(false);
      onMuteToggle?.(false);
      const ctx = contextForWorker(false);
      if (!projectIntroduction?.trim()) {
        ctx.custom_fields = { ...ctx.custom_fields, force_project_scope: '1' };
      }
      onContext?.(ctx);
    } catch (err) {
      const raw = err instanceof Error ? err.message : 'Voice setup failed';
      const message =
        /permission denied/i.test(raw) || /NotAllowedError/i.test(raw)
          ? 'Microphone blocked. On this Mac use http://127.0.0.1:3000 and allow mic when prompted.'
          : raw;
      setVoiceError(message);
      setState('Muted');
      setMuted(true);
      setSessionActive(false);
      micRef.current?.dispose();
      micRef.current = null;
      onMuteToggle?.(true);
    } finally {
      setConnecting(false);
    }
  };

  const setMicMuted = async (micMuted: boolean) => {
    if (!sessionActive) return;
    const ctx = contextForWorker(micMuted);
    onContext?.(ctx);
    setVoiceError(null);
    setMuted(micMuted);
    const endingUtterance = micMuted && !muted;
    setState(micMuted ? (endingUtterance ? 'Transcribing' : 'Muted') : 'Listening');
    onMuteToggle?.(micMuted);

    if (endingUtterance && micRef.current) {
      try {
        const blob = await micRef.current.stop();
        await runSttOnBlob(blob);
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Could not capture audio';
        setVoiceError(message);
        setState('Muted');
      }
    } else if (!micMuted) {
      try {
        if (!micRef.current) micRef.current = new MicCaptureSession();
        await micRef.current.start();
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Could not open mic';
        setVoiceError(message);
        setMuted(true);
        setState('Muted');
      }
    }
  };

  const endSession = () => {
    setVoiceError(null);
    pendingTurnFieldsRef.current = null;
    resetFieldsAfterTurnRef.current = false;
    submittedTurnStartedRef.current = false;
    setCustomFields(INITIAL_CUSTOM_FIELDS);
    sessionEventsRef.current?.stop();
    sessionEventsRef.current = null;
    turnAbortRef.current?.abort();
    turnAbortRef.current = null;
    activeTurnIdRef.current = null;
    micRef.current?.dispose();
    micRef.current = null;
    setSessionActive(false);
    setState('Muted');
    setMuted(true);
    onMuteToggle?.(true);
  };

  const cancelTurn = () => {
    const turnId = activeTurnIdRef.current;
    turnAbortRef.current?.abort();
    turnAbortRef.current = null;
    if (turnId) void abortVoiceTurn(turnId, threadId);
    emitDock({ type: 'turn_aborted', turn_id: turnId });
    setState(muted ? 'Muted' : 'Listening');
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
            <p className="text-[11px] text-slate-500">Colab STT · text replies in dock</p>
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

      {state === 'Transcribing' ? (
        <section className="glass-panel flex items-center gap-2.5 rounded-xl px-3 py-3">
          <LoaderCircle className="h-4 w-4 shrink-0 animate-spin text-cyan-400" aria-hidden />
          <p className="text-xs leading-relaxed text-slate-300">
            Transcribing your message…
          </p>
        </section>
      ) : null}

      {state === 'Reviewing' && sttDraft !== null ? (
        <section className="glass-panel space-y-2 rounded-xl p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Review transcript
          </p>
          <textarea
            className="min-h-[5rem] w-full rounded-lg border border-slate-700/80 bg-[#0a0e16] p-2 text-sm text-slate-200"
            value={sttDraft}
            onChange={(e) => setSttDraft(e.target.value)}
          />
          <div className="flex gap-2">
            <button
              type="button"
              className="flex-1 rounded-lg bg-cyan-600 px-3 py-2 text-xs font-semibold text-white"
              onClick={() => {
                if (!sttDraft.trim()) return;
                void sendReviewedTurn(sttDraft.trim());
              }}
            >
              Send
            </button>
            <button
              type="button"
              className="flex-1 rounded-lg border border-slate-600 px-3 py-2 text-xs text-slate-200"
              onClick={() => {
                setSttDraft(null);
                setState('Muted');
              }}
            >
              Discard
            </button>
          </div>
        </section>
      ) : null}

      <MotionButtons
        connected={connected}
        connecting={connecting}
        live={live}
        state={state}
        onStart={() => void startSession()}
        onToggleMute={() => void setMicMuted(!muted)}
        onEnd={endSession}
      />

      {state === 'Streaming' || state === 'Processing' ? (
        <button
          type="button"
          className="w-full rounded-lg border border-rose-600/50 px-3 py-2 text-xs font-medium text-rose-200"
          onClick={cancelTurn}
        >
          Stop turn
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
            onContext?.(contextForWorker(muted));
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
        {state === 'Thinking' || connecting ? 'Starting…' : 'Start voice session'}
      </button>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        disabled={connecting || state === 'Processing' || state === 'Streaming'}
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

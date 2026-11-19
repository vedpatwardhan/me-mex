import React, { useEffect, useMemo, useRef, useState } from 'react';

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
  const togglingRef = useRef(false);
  const setVoiceStateRef = useRef(setState);
  useEffect(() => {
    setVoiceStateRef.current = setState;
  });

  const threadId = useMemo(
    () => `voice-${projectId || 'default'}`,
    [projectId],
  );

  const buildContext = (): VoiceContext => ({
    active_project_id: projectId || '',
    muted,
    custom_fields: parseCustomFields(customFields),
    selected_node_ids: selectedNodeId ? [selectedNodeId] : [],
    thread_id: threadId,
  });

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

  useEffect(() => {
    const session = sessionRef.current;
    if (!session?.isReady()) return;
    void session.publishContext(buildContext());
    // eslint-disable-next-line react-hooks/exhaustive-deps -- republish on project/selection change
  }, [projectId, selectedNodeId, threadId]);

  const roomReady = sessionRef.current?.isReady() ?? false;
  const connected =
    roomReady &&
    (state === 'Listening' ||
      state === 'Speaking' ||
      state === 'Awaiting approval' ||
      (muted && state === 'Muted'));
  const live = connected && !muted && state === 'Listening';

  const startSession = async () => {
    if (togglingRef.current) return;
    togglingRef.current = true;
    const session = ensureSession();
    const ctx = { ...buildContext(), muted: false };
    onContext?.(ctx);
    setVoiceError(null);
    try {
      setState('Thinking');
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
      await session.setMuted(false, scopeCtx);
      setState('Listening');
      setMuted(false);
      onMuteToggle?.(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Voice connection failed';
      setVoiceError(message);
      setState('Muted');
      setMuted(true);
      onMuteToggle?.(true);
      await session.disconnect();
    } finally {
      togglingRef.current = false;
    }
  };

  const setMicMuted = async (micMuted: boolean) => {
    if (togglingRef.current) return;
    const session = ensureSession();
    if (!session.isReady()) return;
    togglingRef.current = true;
    const ctx = { ...buildContext(), muted: micMuted };
    onContext?.(ctx);
    setVoiceError(null);
    try {
      await session.setMuted(micMuted, ctx);
      setMuted(micMuted);
      setState(micMuted ? 'Muted' : 'Listening');
      onMuteToggle?.(micMuted);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Could not update mic';
      setVoiceError(message);
    } finally {
      togglingRef.current = false;
    }
  };

  const endSession = async () => {
    if (togglingRef.current) return;
    togglingRef.current = true;
    const session = ensureSession();
    setVoiceError(null);
    try {
      await session.disconnect();
      sessionRef.current = null;
      onVoiceSession?.(null);
      setState('Muted');
      setMuted(true);
      onMuteToggle?.(true);
    } finally {
      togglingRef.current = false;
    }
  };

  return (
    <aside className="w-56 shrink-0 border-r border-slate-800 bg-[#0c1018] p-3 flex flex-col gap-3">
      <div className="text-xs uppercase tracking-wide text-slate-500">Voice rail</div>
      <div className="text-sm text-slate-300">Project: {projectId || '—'}</div>
      {!connected ? (
        <button
          type="button"
          disabled={state === 'Thinking'}
          onClick={() => void startSession()}
          className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-60"
        >
          {state === 'Thinking' ? 'Connecting…' : 'Start voice session'}
        </button>
      ) : (
        <div className="flex flex-col gap-2">
          <button
            type="button"
            disabled={togglingRef.current || state === 'Thinking'}
            onClick={() => void setMicMuted(!muted)}
            className={`rounded-md px-3 py-2 text-sm font-medium text-white ${
              live ? 'bg-emerald-700 hover:bg-emerald-600' : 'bg-amber-700 hover:bg-amber-600'
            } disabled:opacity-60`}
          >
            {live ? 'Mute mic' : 'Unmute mic'}
          </button>
          <button
            type="button"
            disabled={togglingRef.current}
            onClick={() => void endSession()}
            className="rounded-md border border-slate-600 px-3 py-2 text-sm text-slate-200 hover:bg-slate-800"
          >
            End session
          </button>
        </div>
      )}
      <div className="text-xs text-slate-400">
        Status: {state}
        {connected ? (live ? ' · mic on' : ' · mic off (session active)') : ' · not connected'}
      </div>
      {connected && muted ? (
        <button
          type="button"
          className="rounded border border-slate-600 px-2 py-1 text-xs text-slate-200"
          onClick={() => {
            const s = ensureSession();
            if (s.isReady()) void s.sendAgentTurn('', { ...buildContext(), muted: true });
          }}
        >
          Send muted turn (custom fields)
        </button>
      ) : null}
      {!projectIntroduction?.trim() && connected ? (
        <p className="text-xs text-cyan-400/90">Unmute to set project scope (P1).</p>
      ) : null}
      {voiceError ? (
        <div className="text-xs text-rose-400 break-words" role="alert">
          {voiceError}
        </div>
      ) : null}
      <label className="text-xs text-slate-500">Custom fields</label>
      <textarea
        className="h-28 w-full rounded border border-slate-700 bg-slate-900 p-2 text-xs text-slate-200"
        value={customFields}
        onChange={(e) => {
          setCustomFields(e.target.value);
          const ctx = buildContext();
          onContext?.(ctx);
          const s = ensureSession();
          if (s.isReady()) void s.publishContext(ctx);
        }}
        spellCheck={false}
      />
    </aside>
  );
};

import React, { useEffect, useMemo, useRef, useState } from 'react';

import type { VoiceContext } from '../services/voiceSession';
import { VoiceSession } from '../services/voiceSession';
import type { VoiceSessionState } from '../services/livekitService';
import { parseCustomFields } from '../utils/dockUtils';

type Props = {
  projectId?: string;
  selectedNodeId?: string | null;
  onMuteToggle?: (muted: boolean) => void;
  onContext?: (ctx: VoiceContext) => void;
};

export const VoiceRail: React.FC<Props> = ({
  projectId,
  selectedNodeId,
  onMuteToggle,
  onContext,
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
      sessionRef.current = new VoiceSession((s) => setVoiceStateRef.current(s));
    }
    return sessionRef.current;
  };

  const live = !muted && state === 'Listening';

  const toggleMute = async () => {
    if (togglingRef.current) return;
    togglingRef.current = true;
    const nextMuted = !muted;
    const session = ensureSession();
    const ctx = { ...buildContext(), muted: nextMuted };
    onContext?.(ctx);
    setVoiceError(null);
    try {
      if (!nextMuted) {
        setState('Thinking');
        if (!session.isReady()) {
          await session.connect(`user-${projectId || 'me'}-${Date.now()}`);
        }
        if (!session.isReady()) {
          throw new Error('Could not join LiveKit room');
        }
        await session.setMuted(false, ctx);
        setState('Listening');
        setMuted(false);
        onMuteToggle?.(false);
      } else {
        await session.setMuted(true, ctx);
        await session.disconnect();
        setState('Muted');
        setMuted(true);
        onMuteToggle?.(true);
      }
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

  return (
    <aside className="w-56 shrink-0 border-r border-slate-800 bg-[#0c1018] p-3 flex flex-col gap-3">
      <div className="text-xs uppercase tracking-wide text-slate-500">Voice rail</div>
      <div className="text-sm text-slate-300">Project: {projectId || '—'}</div>
      <button
        type="button"
        disabled={state === 'Thinking'}
        onClick={() => void toggleMute()}
        className={`rounded-md px-3 py-2 text-sm font-medium text-white ${
          live ? 'bg-emerald-700 hover:bg-emerald-600' : 'bg-indigo-600 hover:bg-indigo-500'
        } disabled:opacity-60`}
      >
        {state === 'Thinking'
          ? 'Connecting…'
          : live
            ? 'Listening — click to end'
            : 'Start voice session'}
      </button>
      <div className="text-xs text-slate-400">
        Status: {state}
        {live ? ' · mic on' : muted ? ' · mic off' : ''}
      </div>
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

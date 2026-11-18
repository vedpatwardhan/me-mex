import React, { useMemo, useRef, useState } from 'react';

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
  const sessionRef = useRef<VoiceSession | null>(null);

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
      sessionRef.current = new VoiceSession(setState);
    }
    return sessionRef.current;
  };

  const toggleMute = async () => {
    const nextMuted = !muted;
    setMuted(nextMuted);
    onMuteToggle?.(nextMuted);
    const session = ensureSession();
    const ctx = buildContext();
    ctx.muted = nextMuted;
    onContext?.(ctx);
    if (!session.room && !nextMuted) {
      await session.connect(`user-${projectId || 'me'}`);
    }
    if (session.room) {
      await session.setMuted(nextMuted, ctx);
      await session.publishContext(ctx);
    }
    if (nextMuted) {
      await session.disconnect();
    }
  };

  return (
    <aside className="w-56 shrink-0 border-r border-slate-800 bg-[#0c1018] p-3 flex flex-col gap-3">
      <div className="text-xs uppercase tracking-wide text-slate-500">Voice rail</div>
      <div className="text-sm text-slate-300">Project: {projectId || '—'}</div>
      <button
        type="button"
        onClick={() => void toggleMute()}
        className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white"
      >
        {muted ? 'Unmute to begin (P1)' : 'Mute (W8)'}
      </button>
      <div className="text-xs text-slate-400">State: {state}</div>
      <label className="text-xs text-slate-500">Custom fields</label>
      <textarea
        className="h-28 w-full rounded border border-slate-700 bg-slate-900 p-2 text-xs text-slate-200"
        value={customFields}
        onChange={(e) => {
          setCustomFields(e.target.value);
          const ctx = buildContext();
          onContext?.(ctx);
          void ensureSession().publishContext(ctx);
        }}
        spellCheck={false}
      />
    </aside>
  );
};

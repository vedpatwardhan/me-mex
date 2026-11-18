import React, { useState } from 'react';
import type { VoiceSessionState } from '../services/livekitService';

type Props = {
  projectId?: string;
  onMuteToggle?: (muted: boolean) => void;
};

export const VoiceRail: React.FC<Props> = ({ projectId, onMuteToggle }) => {
  const [muted, setMuted] = useState(true);
  const [state, setState] = useState<VoiceSessionState>('Muted');
  const [customFields, setCustomFields] = useState('arxiv_id=\nroot_id=');

  const toggleMute = () => {
    const next = !muted;
    setMuted(next);
    setState(next ? 'Muted' : 'Listening');
    onMuteToggle?.(next);
  };

  return (
    <aside className="w-56 shrink-0 border-r border-slate-800 bg-[#0c1018] p-3 flex flex-col gap-3">
      <div className="text-xs uppercase tracking-wide text-slate-500">Voice rail</div>
      <div className="text-sm text-slate-300">Project: {projectId || '—'}</div>
      <button
        type="button"
        onClick={toggleMute}
        className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white"
      >
        {muted ? 'Unmute to begin (P1)' : 'Mute (W8)'}
      </button>
      <div className="text-xs text-slate-400">State: {state}</div>
      <label className="text-xs text-slate-500">Custom fields</label>
      <textarea
        className="h-28 w-full rounded border border-slate-700 bg-slate-900 p-2 text-xs text-slate-200"
        value={customFields}
        onChange={(e) => setCustomFields(e.target.value)}
        spellCheck={false}
      />
    </aside>
  );
};

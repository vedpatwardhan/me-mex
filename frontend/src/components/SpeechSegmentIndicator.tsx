import React from 'react';
import { Timer } from 'lucide-react';

import type { SpeechSegmentTimer } from '../hooks/useSpeechSegmentTimer';

function formatSec(ms: number): string {
  return `${(ms / 1000).toFixed(1)}s`;
}

type Props = {
  timer: SpeechSegmentTimer;
  visible: boolean;
};

export const SpeechSegmentIndicator: React.FC<Props> = ({ timer, visible }) => {
  if (!visible) return null;

  const { unmutedMs, capMs, warn, overCap } = timer;
  const capSec = capMs / 1000;

  const barPct = Math.min(100, (unmutedMs / capMs) * 100);
  const ring = overCap
    ? 'border-rose-500/50 bg-rose-500/15'
    : warn
      ? 'border-amber-500/45 bg-amber-500/10'
      : 'border-emerald-500/35 bg-emerald-500/10';
  const text = overCap ? 'text-rose-200' : warn ? 'text-amber-200' : 'text-emerald-100';

  return (
    <div className={`rounded-xl border px-3 py-2.5 ${ring}`} role="status" aria-live="polite">
      <div className="flex items-center justify-between gap-2">
        <div className={`flex items-center gap-1.5 text-sm font-semibold tabular-nums ${text}`}>
          <Timer className="h-3.5 w-3.5 shrink-0 opacity-80" />
          {formatSec(unmutedMs)}
          <span className="text-xs font-normal opacity-70">/ {capSec}s</span>
        </div>
        <span className="text-[10px] uppercase tracking-wide text-slate-400">Mic open</span>
      </div>
      <p className="mt-1 text-[11px] text-slate-400">
        Mute when finished — that sends the turn (not silence).
      </p>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-800/80">
        <div
          className={`h-full rounded-full transition-[width] duration-100 ${
            overCap ? 'bg-rose-500' : warn ? 'bg-amber-500' : 'bg-emerald-500'
          }`}
          style={{ width: `${barPct}%` }}
        />
      </div>
      {overCap ? (
        <p className="mt-2 text-xs font-medium leading-snug text-rose-200">
          Limit reached — mute to send this clip, then unmute for more.
        </p>
      ) : warn ? (
        <p className="mt-2 text-xs leading-snug text-amber-200/90">
          Approaching limit — mute soon to send, then unmute for the next part.
        </p>
      ) : null}
    </div>
  );
};

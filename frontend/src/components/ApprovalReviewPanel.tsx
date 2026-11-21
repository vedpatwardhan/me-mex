import React from 'react';

import { DockMarkdown } from './DockMarkdown';

type Props = {
  reviewMarkdown: string;
  open: boolean;
  onClose: () => void;
};

export const ApprovalReviewPanel: React.FC<Props> = ({ reviewMarkdown, open, onClose }) => {
  if (!open) return null;
  return (
    <div className="mt-3 rounded-lg border border-cyan-500/25 bg-slate-950/80 p-2.5">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-cyan-300/90">
          Review before approve
        </span>
        <button
          type="button"
          className="text-[10px] text-slate-400 hover:text-slate-200"
          onClick={onClose}
        >
          Close
        </button>
      </div>
      <div className="max-h-64 overflow-y-auto rounded-md border border-white/5 bg-[#0a0e16] p-2">
        <DockMarkdown>{reviewMarkdown}</DockMarkdown>
      </div>
    </div>
  );
};

import React, { useState } from 'react';
import { LayoutList, LoaderCircle, Sparkles, User, Bot } from 'lucide-react';

import { ApprovalReviewPanel } from './ApprovalReviewPanel';
import { DockMarkdown } from './DockMarkdown';

export type DockItem = {
  id: string;
  className: 'nudge' | 'approval' | 'informational' | 'job';
  title: string;
  detail?: string;
  approvalType?: string;
  reviewMarkdown?: string;
  payload?: Record<string, unknown>;
  linkedJobId?: string;
  approvalId?: string;
};

type Props = {
  latestReply?: string;
  latestUserText?: string;
  items?: DockItem[];
  pendingApprovals?: Set<string>;
  projectScope?: string;
  onApprove?: (id: string) => void;
  onDismiss?: (id: string) => void;
};

const ITEM_STYLES: Record<
  DockItem['className'],
  { badge: string; border: string; label: string }
> = {
  nudge: {
    label: 'Nudge',
    badge: 'tag-purple',
    border: 'border-purple-500/25',
  },
  job: {
    label: 'Job',
    badge: 'tag-yellow',
    border: 'border-amber-500/25',
  },
  approval: {
    label: 'Approval',
    badge: 'tag-cyan',
    border: 'border-cyan-500/30',
  },
  informational: {
    label: 'Info',
    badge: 'bg-slate-700/80 text-slate-300 border border-slate-600/60',
    border: 'border-slate-600/40',
  },
};

export const RecommendationsDock: React.FC<Props> = ({
  latestReply = '',
  latestUserText = '',
  items = [],
  pendingApprovals = new Set(),
  projectScope = '',
  onApprove,
  onDismiss,
}) => {
  const [reviewId, setReviewId] = useState<string | null>(null);

  return (
    <aside className="flex w-[22rem] shrink-0 flex-col border-l border-white/10 bg-[#0c1018]/95 overflow-hidden">
      <header className="shrink-0 border-b border-white/5 px-4 py-4">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-violet-500/30 bg-violet-500/10">
            <LayoutList className="h-4 w-4 text-violet-400" />
          </span>
          <div>
            <h2 className="text-sm font-semibold tracking-tight text-slate-100">
              Recommendations
            </h2>
            <p className="text-[11px] text-slate-500">Project scope, queue, latest turn</p>
          </div>
        </div>
      </header>

      <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-4 py-4">
        {projectScope ? (
          <section className="glass-panel rounded-xl p-3 pb-4">
            <div className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              <Sparkles className="h-3.5 w-3.5 text-emerald-400" />
              Committed project scope
            </div>
            <DockMarkdown>{projectScope}</DockMarkdown>
          </section>
        ) : (
          <section className="rounded-xl border border-dashed border-slate-700/80 px-3 py-3 text-xs text-slate-500">
            No committed scope yet. Approve a scope proposal in the queue to commit.
          </section>
        )}

        <section className="flex flex-col gap-2">
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Queue ({items.length})
          </h3>
          <ul className="space-y-2.5">
            {items.length === 0 ? (
              <li className="rounded-xl border border-dashed border-slate-700/70 px-3 py-4 text-center text-xs text-slate-500">
                Nothing pending — approvals and jobs appear after turns.
              </li>
            ) : (
              items.map((item) => {
                const style = ITEM_STYLES[item.className];
                const reviewOpen = reviewId === item.id;
                const reviewBody = item.reviewMarkdown || '_Loading preview…_';
                const isApproving = pendingApprovals.has(item.id);
                return (
                  <li
                    key={item.id}
                    className={`glass-panel rounded-xl border px-3 py-2.5 ${style.border}`}
                  >
                    <div className="flex flex-wrap items-start gap-2">
                      <span
                        className={`provenance-highlight shrink-0 px-2 py-0.5 text-[10px] uppercase tracking-wide ${style.badge}`}
                      >
                        {style.label}
                      </span>
                      <p className="flex-1 text-sm font-medium leading-snug text-slate-100">
                        {item.title}
                      </p>
                    </div>
                    {item.detail ? (
                      <p className="mt-2 text-xs leading-relaxed text-slate-400">{item.detail}</p>
                    ) : null}
                    {item.className === 'approval' && onApprove && onDismiss ? (
                      <>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button
                            type="button"
                            disabled={isApproving}
                            className="rounded-lg border border-cyan-600/50 bg-cyan-950/40 px-3 py-1 text-xs font-medium text-cyan-200 hover:bg-cyan-900/40 disabled:cursor-not-allowed disabled:opacity-50"
                            onClick={() => setReviewId(reviewOpen ? null : item.id)}
                          >
                            Review
                          </button>
                          <button
                            type="button"
                            disabled={isApproving}
                            aria-busy={isApproving}
                            className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1 text-xs font-semibold text-white hover:bg-emerald-500 disabled:cursor-wait disabled:opacity-75"
                            onClick={() => onApprove(item.id)}
                          >
                            {isApproving ? (
                              <>
                                <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                                Approving…
                              </>
                            ) : (
                              'Approve'
                            )}
                          </button>
                          <button
                            type="button"
                            disabled={isApproving}
                            className="rounded-lg border border-slate-600 bg-slate-800/80 px-3 py-1 text-xs font-medium text-slate-200 hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
                            onClick={() => onDismiss(item.id)}
                          >
                            Dismiss
                          </button>
                        </div>
                        <ApprovalReviewPanel
                          reviewMarkdown={reviewBody}
                          open={reviewOpen}
                          onClose={() => setReviewId(null)}
                        />
                      </>
                    ) : null}
                  </li>
                );
              })
            )}
          </ul>
        </section>

        <section className="glass-panel-elevated space-y-3 rounded-xl p-3">
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Latest turn
          </h3>
          {latestUserText ? (
            <div className="space-y-1.5">
              <div className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wide text-slate-500">
                <User className="h-3 w-3" />
                You
              </div>
              <p className="rounded-lg border border-slate-700/60 bg-slate-900/60 px-2.5 py-2 text-sm leading-relaxed text-slate-300 whitespace-pre-wrap">
                {latestUserText}
              </p>
            </div>
          ) : null}
          <div className="space-y-1.5">
            <div className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wide text-slate-500">
              <Bot className="h-3 w-3" />
              Assistant
            </div>
            <div className="min-h-[3rem] rounded-lg border border-sky-500/20 bg-sky-500/5 px-2.5 py-2">
              {latestReply ? (
                <DockMarkdown>{latestReply}</DockMarkdown>
              ) : (
                <p className="text-sm text-slate-500">—</p>
              )}
            </div>
          </div>
        </section>

      </div>
    </aside>
  );
};

import React, { useState } from 'react';

import type { DockTurn, JobHistoryRow } from '../utils/dockStreamReducer';
import {
  LayoutList,
  LoaderCircle,
  Pause,
  Play,
  Sparkles,
  Trash2,
  User,
  Bot,
  X,
} from 'lucide-react';

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
  jobStatus?: string;
  approvalResolution?: string;
};

type Props = {
  latestReply?: string;
  latestUserText?: string;
  turns?: DockTurn[];
  jobHistory?: JobHistoryRow[];
  items?: DockItem[];
  onRevertTurn?: (turnId: string) => void;
  pendingApprovals?: Set<string>;
  pendingJobActions?: Set<string>;
  projectScope?: string;
  onApprove?: (id: string) => void;
  onDismiss?: (id: string) => void;
  onPauseJob?: (id: string) => void;
  onResumeJob?: (id: string) => void;
  onCancelJob?: (id: string) => void;
  onDeleteJob?: (id: string) => void;
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
  turns = [],
  jobHistory = [],
  items = [],
  onRevertTurn,
  pendingApprovals = new Set(),
  pendingJobActions = new Set(),
  projectScope = '',
  onApprove,
  onDismiss,
  onPauseJob,
  onResumeJob,
  onCancelJob,
  onDeleteJob,
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
                const isJobActionPending = pendingJobActions.has(item.id);
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
                    {item.className === 'job' ? (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {item.jobStatus === 'running' && onPauseJob ? (
                          <button
                            type="button"
                            disabled={isJobActionPending}
                            className="inline-flex items-center gap-1 rounded-lg border border-amber-600/50 bg-amber-950/40 px-2.5 py-1 text-xs text-amber-100 disabled:opacity-50"
                            onClick={() => onPauseJob(item.id)}
                          >
                            <Pause className="h-3 w-3" /> Pause
                          </button>
                        ) : null}
                        {item.jobStatus === 'paused' && onResumeJob ? (
                          <button
                            type="button"
                            disabled={isJobActionPending}
                            className="inline-flex items-center gap-1 rounded-lg border border-emerald-600/50 bg-emerald-950/40 px-2.5 py-1 text-xs text-emerald-100 disabled:opacity-50"
                            onClick={() => onResumeJob(item.id)}
                          >
                            <Play className="h-3 w-3" /> Resume
                          </button>
                        ) : null}
                        {['running', 'paused'].includes(item.jobStatus || '') && onCancelJob ? (
                          <button
                            type="button"
                            disabled={isJobActionPending}
                            className="inline-flex items-center gap-1 rounded-lg border border-rose-600/50 bg-rose-950/40 px-2.5 py-1 text-xs text-rose-100 disabled:opacity-50"
                            onClick={() => onCancelJob(item.id)}
                          >
                            <X className="h-3 w-3" /> Cancel
                          </button>
                        ) : null}
                        {['done', 'cancelled', 'dismissed', 'error'].includes(
                          item.jobStatus || '',
                        ) && onDeleteJob ? (
                          <button
                            type="button"
                            disabled={isJobActionPending}
                            className="inline-flex items-center gap-1 rounded-lg border border-slate-600 bg-slate-800/80 px-2.5 py-1 text-xs text-slate-200 disabled:opacity-50"
                            onClick={() => onDeleteJob(item.id)}
                          >
                            <Trash2 className="h-3 w-3" /> Remove
                          </button>
                        ) : null}
                      </div>
                    ) : null}
                  </li>
                );
              })
            )}
          </ul>
        </section>

        <section className="glass-panel-elevated space-y-3 rounded-xl p-3">
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Turn thread ({turns.length || (latestUserText ? 1 : 0)})
          </h3>
          <ul className="space-y-3 max-h-64 overflow-y-auto">
            {(turns.length ? turns : latestUserText ? [{ turnId: 'latest', userText: latestUserText, assistantText: latestReply }] : []).map(
              (turn) => (
                <li key={turn.turnId} className="relative space-y-1.5 pb-2 border-b border-white/5 last:border-0">
                  <span className="text-[10px] text-slate-500 flex items-center gap-1">
                    <User className="h-3 w-3" /> You
                  </span>
                  <p className="rounded-lg border border-slate-700/60 bg-slate-900/60 px-2.5 py-2 pr-16 text-sm text-slate-300 whitespace-pre-wrap">
                    {turn.userText}
                  </p>
                  {onRevertTurn && turn.turnId !== 'latest' ? (
                    <button
                      type="button"
                      className="absolute bottom-3 right-2 text-[10px] uppercase tracking-wide text-rose-300/90 hover:text-rose-200"
                      onClick={() => {
                        if (
                          window.confirm(
                            'Revert from this turn? Later turns and their graph changes will be removed.',
                          )
                        ) {
                          onRevertTurn(turn.turnId);
                        }
                      }}
                    >
                      Revert
                    </button>
                  ) : null}
                  {turn.assistantText ? (
                    <>
                      <span className="text-[10px] text-slate-500 flex items-center gap-1">
                        <Bot className="h-3 w-3" /> Assistant
                      </span>
                      <div className="rounded-lg border border-sky-500/20 bg-sky-500/5 px-2.5 py-2 text-sm">
                        <DockMarkdown>{turn.assistantText}</DockMarkdown>
                      </div>
                    </>
                  ) : null}
                </li>
              ),
            )}
            {!turns.length && !latestUserText ? (
              <li className="text-xs text-slate-500">No turns yet.</li>
            ) : null}
          </ul>
        </section>

        <section className="space-y-2">
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Job history ({jobHistory.length})
          </h3>
          <ul className="max-h-48 space-y-1.5 overflow-y-auto text-xs text-slate-400">
            {jobHistory.length === 0 ? (
              <li className="rounded-lg border border-dashed border-slate-700/70 px-3 py-3 text-center">
                No job runs recorded yet.
              </li>
            ) : (
              jobHistory.map((job) => (
                <li
                  key={job.job_id}
                  className="rounded-lg border border-slate-700/50 bg-slate-900/40 px-2.5 py-2"
                >
                  <p className="font-medium text-slate-200">
                    {job.label || job.worker || job.job_id}
                  </p>
                  <p>
                    {job.worker} · {job.status}
                  </p>
                  {job.output_summary ? (
                    <p className="mt-1 line-clamp-2 text-slate-500">{job.output_summary}</p>
                  ) : null}
                </li>
              ))
            )}
          </ul>
        </section>

      </div>
    </aside>
  );
};

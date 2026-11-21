import type { DockItem } from '../components/RecommendationsDock';
import { formatApprovalReview } from './approvalPreview';
import { dedupeApprovalJobs, sortQueueItems } from './dockQueueSort';

export type DockStreamState = {
  latestReply: string;
  latestUserText: string;
  items: DockItem[];
};

export const emptyDockStreamState = (): DockStreamState => ({
  latestReply: '',
  latestUserText: '',
  items: [],
});

function finalizeItems(items: DockItem[]): DockItem[] {
  return sortQueueItems(dedupeApprovalJobs(items));
}

function upsertApproval(items: DockItem[], ev: Record<string, unknown>): DockItem[] {
  const approvalId = (ev.approval_id as string) || (ev.id as string);
  if (!approvalId) return items;
  const approvalType =
    (ev.approval_type as string) || (ev.approvalType as string) || undefined;
  const payload = ev.payload as Record<string, unknown> | undefined;
  const title =
    (ev.title as string) ||
    (typeof ev.content === 'string' ? ev.content : 'Pending approval');
  const reviewMarkdown =
    (ev.reviewMarkdown as string) ||
    (approvalType && payload ? formatApprovalReview(approvalType, payload) : undefined);
  const existing = items.find((i) => i.id === approvalId && i.className === 'approval');
  const row: DockItem = {
    id: approvalId,
    className: 'approval',
    title,
    detail: approvalType || existing?.detail || 'approval',
    approvalType,
    payload: payload ?? existing?.payload,
    reviewMarkdown: reviewMarkdown ?? existing?.reviewMarkdown,
    linkedJobId: (ev.linkedJobId as string) || existing?.linkedJobId,
  };
  return finalizeItems([row, ...items.filter((i) => !(i.id === approvalId && i.className === 'approval'))]);
}

function upsertJob(items: DockItem[], job: Record<string, unknown>): DockItem[] {
  const jobId = (job.job_id as string) || `job-${job.worker || 'task'}`;
  const approvalId =
    (job.approval_id as string) ||
    (job.recommendation_id as string) ||
    undefined;
  const row: DockItem = {
    id: jobId,
    className: 'job',
    title: (job.label as string) || String(job.worker || 'Job'),
    detail: `${job.worker || 'worker'} · ${job.status || 'running'}`,
    approvalId,
    linkedJobId: jobId,
  };
  let next = [row, ...items.filter((i) => !(i.id === jobId && i.className === 'job'))];
  if (job.status === 'awaiting_approval' && approvalId) {
    next = upsertApproval(next, {
      approval_id: approvalId,
      title: row.title,
      approval_type: job.worker,
      linkedJobId: jobId,
    });
  }
  return finalizeItems(next);
}

export function resetTurnState(state: DockStreamState, userText?: string): DockStreamState {
  return {
    ...state,
    latestReply: '',
    latestUserText: userText ?? state.latestUserText,
  };
}

export function applyStreamEvent(
  state: DockStreamState,
  ev: Record<string, unknown>,
): DockStreamState {
  const type = ev.type as string | undefined;
  if (!type) return state;

  if (type === 'token' && typeof ev.content === 'string') {
    return { ...state, latestReply: state.latestReply + ev.content };
  }
  if (type === 'reply' && typeof ev.content === 'string') {
    return { ...state, latestReply: ev.content };
  }
  if (type === 'approval' || type === 'awaiting_approval') {
    return { ...state, items: upsertApproval(state.items, ev) };
  }
  if (type === 'custom') {
    const jobPatch = ev.job as Record<string, unknown> | undefined;
    if (jobPatch) return { ...state, items: upsertJob(state.items, jobPatch) };
    return state;
  }
  // Proactive notices (e.g. an approval is ready) are status updates, not
  // assistant transcript content for the latest conversational turn.
  if (type === 'proactive_reply') return state;
  if (type === 'assistant_followup' && typeof ev.text === 'string') {
    return { ...state, latestReply: ev.text };
  }
  if (type === 'job_update') {
    const jobPatch = ev.job as Record<string, unknown> | undefined;
    if (jobPatch) return { ...state, items: upsertJob(state.items, jobPatch) };
  }
  if (type === 'recommendation') {
    const cards = (ev.cards as Array<Record<string, unknown>>) || [];
    let items = state.items;
    for (const card of cards) {
      const className = (card.className as DockItem['className']) || 'nudge';
      if (className === 'approval') {
        items = upsertApproval(items, {
          approval_id: card.id,
          title: card.title,
          approval_type: card.approval_type || card.detail,
          payload: card.payload,
        });
        continue;
      }
      const row: DockItem = {
        id: String(card.id ?? `rec-${items.length}`),
        className,
        title: String(card.title ?? 'Recommendation'),
        detail: String(card.detail ?? ''),
      };
      items = [row, ...items.filter((i) => i.id !== row.id)];
    }
    return { ...state, items: finalizeItems(items) };
  }
  if (type === 'worker_progress') {
    return state;
  }
  if (type === 'turn_end') {
    let next = { ...state };
    const reply = ev.reply as string | undefined;
    if (reply) next = { ...next, latestReply: reply };
    let items = next.items;
    for (const job of (ev.jobs as Record<string, unknown>[]) || []) {
      items = upsertJob(items, job);
    }
    const details = ev.details as
      | { approval_id?: string; status?: string }
      | undefined;
    const approvalId = details?.approval_id;
    if (approvalId && (details?.status === 'approved' || details?.status === 'dismissed')) {
      const resolvedApproval = items.find((item) => item.id === approvalId);
      items = items.filter(
        (item) =>
          item.id !== approvalId &&
          item.id !== resolvedApproval?.linkedJobId &&
          item.approvalId !== approvalId,
      );
    } else if (approvalId) {
      items = upsertApproval(items, {
        approval_id: approvalId,
        title: reply || 'Pending approval',
      });
    }
    return { ...next, items };
  }
  if (type === 'turn_start' && typeof ev.text === 'string') {
    return resetTurnState(state, ev.text);
  }
  if (type === 'dock_events' && Array.isArray(ev.events)) {
    return (ev.events as Record<string, unknown>[]).reduce<DockStreamState>(
      (acc, chunk) => applyStreamEvent(acc, chunk),
      state,
    );
  }
  if (type === 'dock_event') {
    const inner = ev.event as Record<string, unknown> | undefined;
    if (inner) return applyStreamEvent(state, inner);
  }
  return state;
}

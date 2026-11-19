import type { DockItem } from '../components/RecommendationsDock';

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

function upsertApproval(items: DockItem[], ev: Record<string, unknown>): DockItem[] {
  const approvalId = (ev.approval_id as string) || (ev.id as string);
  if (!approvalId) return items;
  const title =
    (ev.title as string) ||
    (typeof ev.content === 'string' ? ev.content : 'Pending approval');
  const row: DockItem = {
    id: approvalId,
    className: 'approval',
    title,
    detail: String(approvalId),
  };
  return [row, ...items.filter((i) => i.id !== approvalId)];
}

function upsertJob(items: DockItem[], job: Record<string, unknown>): DockItem[] {
  const jobId = (job.job_id as string) || `job-${job.worker || 'task'}`;
  const row: DockItem = {
    id: jobId,
    className: 'job',
    title: (job.label as string) || String(job.worker || 'Job'),
    detail: `${job.worker || 'worker'} · ${job.status || 'running'}`,
  };
  return [row, ...items.filter((i) => !(i.id === jobId && i.className === 'job'))];
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
  if (type === 'approval') {
    return { ...state, items: upsertApproval(state.items, ev) };
  }
  if (type === 'custom') {
    const jobPatch = ev.job as Record<string, unknown> | undefined;
    if (jobPatch) return { ...state, items: upsertJob(state.items, jobPatch) };
    return state;
  }
  if (type === 'proactive_reply' && typeof ev.text === 'string') {
    return { ...state, latestReply: ev.text as string };
  }
  if (type === 'job_update') {
    const jobPatch = ev.job as Record<string, unknown> | undefined;
    if (jobPatch) return { ...state, items: upsertJob(state.items, jobPatch) };
  }
  if (type === 'recommendation') {
    const cards = (ev.cards as Array<Record<string, unknown>>) || [];
    let items = state.items;
    for (const card of cards) {
      const row: DockItem = {
        id: String(card.id ?? `rec-${items.length}`),
        className: (card.className as DockItem['className']) || 'nudge',
        title: String(card.title ?? 'Recommendation'),
        detail: '',
      };
      items = [row, ...items.filter((i) => i.id !== row.id)];
    }
    return { ...state, items };
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
    const approvalId = (ev.details as { approval_id?: string } | undefined)?.approval_id;
    if (approvalId) {
      items = upsertApproval(items, { approval_id: approvalId, title: reply || 'Pending' });
    }
    return { ...next, items };
  }
  if (type === 'turn_start' && typeof ev.text === 'string') {
    return resetTurnState(state, ev.text);
  }
  if (type === 'dock_events' && Array.isArray(ev.events)) {
    return (ev.events as Record<string, unknown>[]).reduce(
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

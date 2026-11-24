import type { DockItem } from '../components/RecommendationsDock';
import { formatApprovalReview } from '../utils/approvalPreview';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

export type TurnStreamHandlers = {
  onToken?: (token: string) => void;
  onEvent?: (ev: Record<string, unknown>) => void;
  onTurnEnd?: (body: Record<string, unknown>) => void;
};

export async function streamAgentTurn(
  body: { text: string; thread_id: string; context_json: Record<string, unknown> },
  handlers: TurnStreamHandlers,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/agent/turn/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`stream failed: ${res.status}`);
  }
  const reader = res.body?.getReader();
  if (!reader) return;
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() || '';
    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith('data: ')) continue;
      const ev = JSON.parse(line.slice(6)) as Record<string, unknown>;
      handlers.onEvent?.(ev);
      if (ev.type === 'token' && typeof ev.content === 'string') {
        handlers.onToken?.(ev.content);
      }
      if (ev.type === 'turn_end') {
        handlers.onTurnEnd?.(ev);
      }
      if (ev.type === 'approval') {
        handlers.onEvent?.(ev);
      }
    }
  }
}

export async function fetchApprovals(projectId: string, threadId: string): Promise<DockItem[]> {
  const q = new URLSearchParams({ project_id: projectId, thread_id: threadId });
  const res = await fetch(`${API_BASE}/api/agent/approvals?${q}`);
  if (!res.ok) return [];
  const data = await res.json();
  return (data.items || []).map(
    (item: {
      id: string;
      title: string;
      approval_type: string;
      payload?: Record<string, unknown>;
    }) => {
      const approvalType = item.approval_type;
      const payload = item.payload;
      return {
        id: item.id,
        className: 'approval' as const,
        title: item.title,
        detail: approvalType,
        approvalType,
        payload,
        reviewMarkdown: formatApprovalReview(approvalType, payload),
      };
    },
  );
}

export async function fetchJobs(projectId: string, threadId: string): Promise<DockItem[]> {
  const q = new URLSearchParams({ project_id: projectId, thread_id: threadId });
  const res = await fetch(`${API_BASE}/api/agent/jobs?${q}`);
  if (!res.ok) return [];
  const data = await res.json();
  const openStatuses = new Set(['running', 'paused', 'awaiting_approval']);
  return (data.items || [])
    .filter((job: { status?: string }) => openStatuses.has(String(job.status || 'running')))
    .map(
    (job: {
      job_id: string;
      worker?: string;
      kind?: string;
      label?: string;
      status?: string;
      approval_id?: string;
      recommendation_id?: string;
      approval_resolution?: string;
    }) => ({
      id: job.job_id,
      className: 'job' as const,
      title: job.label || job.worker || job.kind || 'Background job',
      detail: `${job.worker || job.kind || 'worker'} · ${job.status || 'running'}`,
      jobStatus: job.status,
      approvalResolution: job.approval_resolution,
      approvalId: job.approval_id || job.recommendation_id,
      linkedJobId: job.job_id,
    }),
  );
}

export async function fetchNudges(projectId: string): Promise<DockItem[]> {
  const res = await fetch(`${API_BASE}/api/agent/nudges?project_id=${encodeURIComponent(projectId)}`);
  if (!res.ok) return [];
  const data = await res.json();
  return (data.suggestions || []).map(
    (s: { type: string; title: string; node_id?: string }, i: number) => ({
      id: `nudge-${i}-${s.node_id || s.type}`,
      className: 'nudge' as const,
      title: s.title,
      detail: s.type,
    }),
  );
}

export async function resumeApproval(
  body: {
    thread_id: string;
    approval_id: string;
    action: 'approve' | 'dismiss';
    context_json: Record<string, unknown>;
  },
): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/api/agent/resume`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`resume failed: ${res.status}`);
  }
  return res.json();
}

export type JobHistoryRow = {
  job_id: string;
  worker?: string;
  status?: string;
  label?: string;
  source_url?: string;
  output_summary?: string;
  updated_at?: number;
};

export type TurnJournalRow = {
  turn_id: string;
  user_text?: string;
  assistant_text?: string;
};

export async function fetchTurnJournal(threadId: string): Promise<TurnJournalRow[]> {
  const q = new URLSearchParams({ thread_id: threadId });
  const res = await fetch(`${API_BASE}/api/agent/turns?${q}`);
  if (!res.ok) return [];
  const data = await res.json();
  return (data.items || []) as TurnJournalRow[];
}

export async function fetchJobHistory(threadId: string): Promise<JobHistoryRow[]> {
  const q = new URLSearchParams({ thread_id: threadId });
  const res = await fetch(`${API_BASE}/api/agent/jobs/history?${q}`);
  if (!res.ok) return [];
  const data = await res.json();
  return (data.items || []) as JobHistoryRow[];
}

export async function revertTurn(
  projectId: string,
  threadId: string,
  turnId: string,
): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/api/agent/turn/revert`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_id: projectId, thread_id: threadId, turn_id: turnId }),
  });
  if (!res.ok) {
    throw new Error(`revert failed: ${res.status}`);
  }
  return res.json();
}

export type JobAction = 'pause' | 'resume' | 'cancel' | 'delete';

export async function controlJob(
  projectId: string,
  threadId: string,
  jobId: string,
  action: JobAction,
): Promise<Record<string, unknown>> {
  const q = new URLSearchParams({ project_id: projectId, thread_id: threadId });
  const res = await fetch(
    `${API_BASE}/api/agent/jobs/${encodeURIComponent(jobId)}/${action}?${q}`,
    { method: 'POST' },
  );
  if (!res.ok) {
    throw new Error(`job ${action} failed: ${res.status}`);
  }
  return res.json();
}

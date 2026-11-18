import type { DockItem } from '../components/RecommendationsDock';

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
  return (data.items || []).map((item: { id: string; title: string; approval_type: string }) => ({
    id: item.id,
    className: 'approval' as const,
    title: item.title,
    detail: item.approval_type,
  }));
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

import { describe, expect, it, vi } from 'vitest';

import type { DockItem } from '../src/components/RecommendationsDock';
import { controlJob } from '../src/services/dockStreamService';

function mapApproval(item: { id: string; title: string; approval_type: string }): DockItem {
  return {
    id: item.id,
    className: 'approval',
    title: item.title,
    detail: item.approval_type,
  };
}

describe('dockStreamService mapping', () => {
  it('maps approval rows', () => {
    const row = mapApproval({ id: 'a1', title: 'Review', approval_type: 'placement' });
    expect(row.className).toBe('approval');
    expect(row.id).toBe('a1');
  });

  it('posts a selected job action with project/thread scope', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ job_id: 'job-1', status: 'cancelled' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await controlJob('p 1', 'thread-1', 'job-1', 'cancel');

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/agent/jobs/job-1/cancel?'),
      { method: 'POST' },
    );
    expect(result.status).toBe('cancelled');
    vi.unstubAllGlobals();
  });
});

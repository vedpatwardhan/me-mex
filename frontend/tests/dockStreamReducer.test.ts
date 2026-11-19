import { describe, expect, it } from 'vitest';

import {
  applyStreamEvent,
  emptyDockStreamState,
} from '../src/utils/dockStreamReducer';

describe('dockStreamReducer', () => {
  it('accumulates tokens', () => {
    const s0 = emptyDockStreamState();
    const s1 = applyStreamEvent(s0, { type: 'token', content: 'Hello' });
    const s2 = applyStreamEvent(s1, { type: 'token', content: ' world' });
    expect(s2.latestReply).toBe('Hello world');
  });

  it('handles job_update without turn_end', () => {
    const s = applyStreamEvent(emptyDockStreamState(), {
      type: 'job_update',
      job: { job_id: 'job-1', label: 'Deep read', status: 'running', worker: 'intradoc' },
    });
    expect(s.items.some((i) => i.id === 'job-1' && i.className === 'job')).toBe(true);
  });

  it('ignores worker_progress for latestReply', () => {
    const s = applyStreamEvent(emptyDockStreamState(), {
      type: 'worker_progress',
      content: 'worker should not show',
    });
    expect(s.latestReply).toBe('');
  });

  it('adds approval on turn_end', () => {
    const s = applyStreamEvent(emptyDockStreamState(), {
      type: 'turn_end',
      reply: 'Review',
      details: { approval_id: 'ap-1' },
    });
    expect(s.items.some((i) => i.id === 'ap-1' && i.className === 'approval')).toBe(true);
  });
});

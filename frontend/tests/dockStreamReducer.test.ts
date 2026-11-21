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

  it('keeps proactive approval notices out of the latest transcript', () => {
    const s0 = applyStreamEvent(emptyDockStreamState(), {
      type: 'token',
      content: 'Let me know more about the project.',
    });
    const s1 = applyStreamEvent(s0, {
      type: 'proactive_reply',
      text: "There's a scope update to review in the dock.",
    });
    expect(s1.latestReply).toBe('Let me know more about the project.');
  });

  it('adds approval on turn_end', () => {
    const s = applyStreamEvent(emptyDockStreamState(), {
      type: 'turn_end',
      reply: 'Review',
      details: { approval_id: 'ap-1' },
    });
    expect(s.items.some((i) => i.id === 'ap-1' && i.className === 'approval')).toBe(true);
  });

  it('maps recommendation approval cards', () => {
    const s = applyStreamEvent(emptyDockStreamState(), {
      type: 'recommendation',
      cards: [
        {
          id: 'appr_x',
          className: 'approval',
          title: 'Scope proposal',
          approval_type: 'project_scope',
          payload: { proposed_introduction: 'My scope' },
        },
      ],
    });
    const row = s.items.find((i) => i.id === 'appr_x');
    expect(row?.className).toBe('approval');
    expect(row?.detail).toBe('project_scope');
    expect(row?.reviewMarkdown).toContain('My scope');
  });

  it('upserts approval on job_update awaiting_approval and hides duplicate job', () => {
    const s = applyStreamEvent(emptyDockStreamState(), {
      type: 'job_update',
      job: {
        job_id: 'job-scope',
        label: 'Project scope',
        status: 'awaiting_approval',
        worker: 'project_scope',
        approval_id: 'appr_abc',
      },
    });
    expect(s.items.some((i) => i.id === 'appr_abc' && i.className === 'approval')).toBe(true);
    expect(s.items.some((i) => i.id === 'job-scope' && i.className === 'job')).toBe(false);
  });

  it('turn_end jobs with approval_id create approval row', () => {
    const s = applyStreamEvent(emptyDockStreamState(), {
      type: 'turn_end',
      reply: 'Done',
      jobs: [
        {
          job_id: 'j1',
          worker: 'project_scope',
          status: 'awaiting_approval',
          approval_id: 'appr_1',
          label: 'Scope',
        },
      ],
    });
    expect(s.items.some((i) => i.id === 'appr_1' && i.className === 'approval')).toBe(true);
  });
});

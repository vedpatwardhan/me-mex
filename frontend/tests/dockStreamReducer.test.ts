import { describe, expect, it } from 'vitest';

import {
  applyStreamEvent,
  emptyDockStreamState,
  flattenDockEvents,
  isGraphWriteEvent,
  isScopeCommittedEvent,
} from '../src/utils/dockStreamReducer';
import { reconcileQueueItems } from '../src/utils/dockQueueSort';

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
    expect(s.items.find((i) => i.id === 'job-1')?.jobStatus).toBe('running');
  });

  it('removes a job row when the user deletes it', () => {
    const withJob = applyStreamEvent(emptyDockStreamState(), {
      type: 'job_update',
      job: { job_id: 'job-delete', label: 'Background gist', status: 'cancelled', worker: 'gist' },
    });
    const deleted = applyStreamEvent(withJob, { type: 'job_delete', job_id: 'job-delete' });
    expect(deleted.items).toEqual([]);
  });

  it('does not restore a job after its approval has been resolved', () => {
    const items = reconcileQueueItems([], [], [
      {
        id: 'job-approved-gist',
        className: 'job',
        title: 'Paper gist',
        jobStatus: 'done',
        approvalResolution: 'approve',
      },
    ]);
    expect(items).toEqual([]);
  });

  it('keeps completed non-approval jobs removable from the queue', () => {
    const items = reconcileQueueItems([], [], [
      {
        id: 'job-readonly-retrieval',
        className: 'job',
        title: 'Graph retrieval',
        jobStatus: 'done',
      },
    ]);
    expect(items.map((item) => item.id)).toEqual(['job-readonly-retrieval']);
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

  it('shows the completed background gist follow-up as the latest assistant turn', () => {
    const state = applyStreamEvent(emptyDockStreamState(), {
      type: 'assistant_followup',
      job_id: 'job-gist',
      text: 'The paper proposes a new predictive model.',
    });
    expect(state.latestReply).toBe('The paper proposes a new predictive model.');
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

  it('removes a resolved approval instead of showing the status as a queue item', () => {
    const pending = applyStreamEvent(
      applyStreamEvent(emptyDockStreamState(), {
        type: 'job_update',
        job: {
          job_id: 'job-scope',
          worker: 'project_scope',
          status: 'awaiting_approval',
          approval_id: 'appr_scope',
        },
      }),
      {
        type: 'awaiting_approval',
        approval_id: 'appr_scope',
        title: 'Review project scope',
      },
    );
    const resolved = applyStreamEvent(pending, {
      type: 'turn_end',
      reply: 'Thanks for approving the project scope.',
      details: {
        approval_id: 'appr_scope',
        status: 'approved',
        scope_committed: true,
      },
    });
    expect(resolved.items).toEqual([]);
    expect(resolved.latestReply).toBe('Thanks for approving the project scope.');
  });

  it('recognizes scope commits inside LiveKit dock event envelopes', () => {
    const events = flattenDockEvents({
      type: 'dock_event',
      event: {
        type: 'dock_event',
        event: {
          type: 'turn_end',
          details: { status: 'approved', approval_type: 'project_scope' },
        },
      },
    });
    expect(events).toHaveLength(1);
    expect(isScopeCommittedEvent(events[0])).toBe(true);
  });

  it('recognizes graph writes from any approved worker response', () => {
    expect(isGraphWriteEvent({ type: 'turn_end', graph_write: true })).toBe(true);
    expect(
      isGraphWriteEvent({ type: 'turn_end', details: { graph_write: true } }),
    ).toBe(true);
    expect(
      isGraphWriteEvent({ type: 'turn_end', details: { status: 'approved' } }),
    ).toBe(true);
    expect(
      isGraphWriteEvent({
        type: 'job_update',
        job: { status: 'done', output: { graph_write: true } },
      }),
    ).toBe(true);
    expect(isGraphWriteEvent({ type: 'turn_end', graph_write: false })).toBe(false);
  });
});

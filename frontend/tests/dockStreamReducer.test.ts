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

  it('adds approval on turn_end', () => {
    const s = applyStreamEvent(emptyDockStreamState(), {
      type: 'turn_end',
      reply: 'Review',
      details: { approval_id: 'ap-1' },
    });
    expect(s.items.some((i) => i.id === 'ap-1' && i.className === 'approval')).toBe(true);
  });
});

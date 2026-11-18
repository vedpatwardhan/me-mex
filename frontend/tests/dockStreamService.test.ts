import { describe, expect, it } from 'vitest';

import type { DockItem } from '../src/components/RecommendationsDock';

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
});

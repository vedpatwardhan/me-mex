import { describe, expect, it } from 'vitest';

import { formatApprovalReview } from '../src/utils/approvalPreview';

describe('formatApprovalReview', () => {
  it('formats project_scope intro', () => {
    const md = formatApprovalReview('project_scope', {
      proposed_introduction: 'Learn RSI and save notes.',
    });
    expect(md).toBe('Learn RSI and save notes.');
  });

  it('shows the proposed gist and source in an approval review', () => {
    const md = formatApprovalReview('gist_root', {
      title: 'Paper title',
      gist: 'A concise source-grounded gist.',
      source_uri: 'https://arxiv.org/pdf/2605.11550',
    });
    expect(md).toContain('Paper title');
    expect(md).toContain('A concise source-grounded gist.');
  });

  it('formats placement candidates', () => {
    const md = formatApprovalReview('placement', {
      root_id: 'n_root',
      candidates: [{ id: 'n_a', title: 'Anchor' }, ['n_b', 0.9]],
    });
    expect(md).toContain('n_root');
    expect(md).toContain('Anchor');
    expect(md).toContain('n_b');
  });

  it('falls back to JSON for unknown types', () => {
    const md = formatApprovalReview('custom_worker', { foo: 1 });
    expect(md).toContain('```json');
    expect(md).toContain('"foo": 1');
  });
});

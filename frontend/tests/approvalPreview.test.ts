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

  it('shows the source and consolidated concept evidence for an intra-doc review', () => {
    const md = formatApprovalReview('intra_doc_staging', {
      source_title: 'Paper title',
      source_url: 'https://example.test/paper.pdf',
      doc_description: 'Whole-document description.',
      concepts: [
        {
          title: 'Method',
          description: 'The source describes the method in detail.',
          passage_indices: [0, 2],
        },
      ],
    });

    expect(md).toContain('Paper title');
    expect(md).toContain('https://example.test/paper.pdf');
    expect(md).toContain('Whole-document description.');
    expect(md).toContain('The source describes the method in detail.');
    expect(md).toContain('Source passages: 0, 2');
  });

  it('falls back to JSON for unknown types', () => {
    const md = formatApprovalReview('custom_worker', { foo: 1 });
    expect(md).toContain('```json');
    expect(md).toContain('"foo": 1');
  });
});

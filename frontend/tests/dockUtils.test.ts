import { describe, expect, it } from 'vitest';
import {
  customFieldsForContext,
  INITIAL_CUSTOM_FIELDS,
  mergeOneShotCustomFields,
  parseCustomFields,
} from '../src/utils/dockUtils';

describe('parseCustomFields', () => {
  it('parses key=value lines', () => {
    const fields = parseCustomFields('arxiv_id=1234.5678\nroot_id=abc');
    expect(fields).toEqual({ arxiv_id: '1234.5678', root_id: 'abc' });
  });

  it('keeps submitted values for the current turn after resetting the textarea', () => {
    const submitted = mergeOneShotCustomFields(null, 'paper=https://example.test/a.pdf');
    const afterReset = mergeOneShotCustomFields(submitted, INITIAL_CUSTOM_FIELDS);
    expect(afterReset).toEqual({ paper: 'https://example.test/a.pdf' });
    expect(INITIAL_CUSTOM_FIELDS).toBe('');
    expect(parseCustomFields(INITIAL_CUSTOM_FIELDS)).toEqual({});
  });

  it('does not carry submitted fields into an unmuted next turn', () => {
    const pending = mergeOneShotCustomFields(null, 'paper=https://example.test/first.pdf');
    const nextTurn = customFieldsForContext(
      pending,
      'paper=https://example.test/second.pdf',
      false,
    );

    expect(nextTurn).toEqual({ paper: 'https://example.test/second.pdf' });
  });

  it('keeps the submitted fields on the muted flush context', () => {
    const pending = mergeOneShotCustomFields(null, 'paper=https://example.test/first.pdf');

    expect(customFieldsForContext(pending, '', true)).toEqual({
      paper: 'https://example.test/first.pdf',
    });
  });
});

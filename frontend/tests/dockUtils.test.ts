import { describe, expect, it } from 'vitest';
import {
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
});

import { describe, expect, it } from 'vitest';
import { parseCustomFields } from '../src/utils/dockUtils';

describe('parseCustomFields', () => {
  it('parses key=value lines', () => {
    const fields = parseCustomFields('arxiv_id=1234.5678\nroot_id=abc');
    expect(fields).toEqual({ arxiv_id: '1234.5678', root_id: 'abc' });
  });
});

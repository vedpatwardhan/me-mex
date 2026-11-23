/** Parse custom_fields textarea (key=value lines) into context_json object. */
export const INITIAL_CUSTOM_FIELDS = '';

export function parseCustomFields(raw: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of raw.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || !trimmed.includes('=')) continue;
    const [key, ...rest] = trimmed.split('=');
    out[key.trim()] = rest.join('=').trim();
  }
  return out;
}

/** Preserve non-empty one-turn fields while the textarea is reset for the next turn. */
export function mergeOneShotCustomFields(
  retained: Record<string, string> | null,
  currentText: string,
): Record<string, string> {
  const merged = { ...(retained || {}) };
  for (const [key, value] of Object.entries(parseCustomFields(currentText))) {
    if (value) merged[key] = value;
  }
  return merged;
}

export function customFieldsForContext(
  pending: Record<string, string> | null,
  currentText: string,
  includePending: boolean,
): Record<string, string> {
  const fields = includePending ? { ...(pending || {}) } : {};
  for (const [key, value] of Object.entries(parseCustomFields(currentText))) {
    if (value) fields[key] = value;
  }
  return fields;
}

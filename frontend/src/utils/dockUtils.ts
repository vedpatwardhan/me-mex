/** Parse custom_fields textarea (key=value lines) into context_json object. */
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

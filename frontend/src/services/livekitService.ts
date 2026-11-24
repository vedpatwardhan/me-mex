/**
 * Phase 2: LiveKit room (local Docker SFU). STT/TTS run on Colab via voice_worker process.
 * Browser Xenova path in voiceService.ts is legacy dev-only.
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

export type VoiceSessionState =
  | 'Muted'
  | 'Listening'
  | 'Reviewing'
  | 'Thinking'
  | 'Speaking'
  | 'Awaiting approval';

export async function fetchLiveKitToken(
  room = 'me-mex',
  identity = `user-${Date.now()}`
): Promise<{ token: string; url: string }> {
  const res = await fetch(`${API_BASE}/api/livekit/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ room, identity }),
  });
  if (!res.ok) {
    throw new Error(`LiveKit token failed: ${res.status}`);
  }
  const body = await res.json();
  return { ...body, url: normalizeTokenLiveKitUrl(body.url) };
}

/** Match loopback host to the page (localhost vs 127.0.0.1). */
function normalizeTokenLiveKitUrl(url: string): string {
  try {
    const u = new URL(url);
    const pageHost = window.location.hostname;
    if (
      (u.hostname === 'localhost' || u.hostname === '127.0.0.1') &&
      (pageHost === 'localhost' || pageHost === '127.0.0.1') &&
      u.hostname !== pageHost
    ) {
      u.hostname = pageHost;
    }
    return u.toString();
  } catch {
    return url;
  }
}

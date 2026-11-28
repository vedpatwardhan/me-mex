/**
 * Browser voice turn: mic capture → STT HTTP → conversation/stream SSE → session/events SSE.
 * Replaces the former LiveKit voice_worker bridge.
 */

import type { VoiceContext } from './voiceTypes';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

export type DockStreamHandler = (ev: Record<string, unknown>) => void;

function parseSseChunk(part: string): Record<string, unknown> | null {
  const line = part.trim();
  if (!line.startsWith('data: ')) return null;
  try {
    return JSON.parse(line.slice(6)) as Record<string, unknown>;
  } catch {
    return null;
  }
}

async function consumeSse(
  res: Response,
  onChunk: (ev: Record<string, unknown>) => void,
  signal?: AbortSignal,
): Promise<void> {
  const reader = res.body?.getReader();
  if (!reader) return;
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    if (signal?.aborted) break;
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() || '';
    for (const part of parts) {
      const ev = parseSseChunk(part);
      if (ev) onChunk(ev);
    }
  }
}

export class MicCaptureSession {
  private stream: MediaStream | null = null;
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];

  async start(): Promise<void> {
    this.dispose();
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : MediaRecorder.isTypeSupported('audio/webm')
        ? 'audio/webm'
        : '';
    this.recorder = mime
      ? new MediaRecorder(this.stream, { mimeType: mime })
      : new MediaRecorder(this.stream);
    this.chunks = [];
    this.recorder.ondataavailable = (e) => {
      if (e.data.size > 0) this.chunks.push(e.data);
    };
    this.recorder.start(200);
  }

  async stop(): Promise<Blob> {
    const recorder = this.recorder;
    if (!recorder || recorder.state === 'inactive') {
      throw new Error('Not recording');
    }
    return new Promise((resolve, reject) => {
      recorder.onstop = () => {
        const type = recorder.mimeType || 'audio/webm';
        const blob = new Blob(this.chunks, { type });
        this.chunks = [];
        this.recorder = null;
        this.stream?.getTracks().forEach((t) => t.stop());
        this.stream = null;
        resolve(blob);
      };
      recorder.onerror = () => reject(new Error('Recording failed'));
      recorder.stop();
    });
  }

  dispose(): void {
    if (this.recorder && this.recorder.state !== 'inactive') {
      try {
        this.recorder.stop();
      } catch {
        /* ignore */
      }
    }
    this.recorder = null;
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    this.chunks = [];
  }
}

export async function transcribeAudio(blob: Blob): Promise<{ text: string; segments?: unknown[] }> {
  const ext = blob.type.includes('wav') ? 'wav' : 'webm';
  const form = new FormData();
  form.append('audio', blob, `utterance.${ext}`);
  const res = await fetch(`${API_BASE}/api/voice/stt/transcribe`, {
    method: 'POST',
    body: form,
  });
  if (res.status === 503) {
    throw new Error('speech_disabled');
  }
  if (!res.ok) {
    throw new Error(`stt_error:${res.status}`);
  }
  const body = (await res.json()) as { text?: string; segments?: unknown[] };
  return { text: (body.text || '').trim(), segments: body.segments };
}

export type StreamVoiceConversationOptions = {
  text: string;
  threadId: string;
  contextJson: Record<string, unknown>;
  turnId?: string;
  onEvent: DockStreamHandler;
  signal?: AbortSignal;
};

export async function streamVoiceConversation(
  opts: StreamVoiceConversationOptions,
): Promise<{ turnId: string; turnEnd?: Record<string, unknown> }> {
  const turnId = opts.turnId || `turn_${Date.now().toString(36)}`;
  const context_json = { ...opts.contextJson, voice_turn: true, turn_id: turnId };
  opts.onEvent({
    type: 'turn_start',
    text: opts.text.slice(0, 8000),
    turn_id: turnId,
  });

  const res = await fetch(`${API_BASE}/api/voice/conversation/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: opts.text,
      thread_id: opts.threadId,
      context_json,
    }),
    signal: opts.signal,
  });
  if (!res.ok) {
    throw new Error(`voice stream failed: ${res.status}`);
  }

  let turnEnd: Record<string, unknown> | undefined;
  let sawToken = false;
  await consumeSse(
    res,
    (ev) => {
      if (ev.type === 'token') {
        sawToken = true;
      }
      opts.onEvent(ev);
      if (ev.type === 'turn_end') turnEnd = ev;
      if (ev.type === 'turn_aborted') turnEnd = ev;
    },
    opts.signal,
  );
  if (sawToken) {
    /* streaming state handled by VoiceRail */
  }
  return { turnId, turnEnd };
}

export async function abortVoiceTurn(turnId: string, threadId: string): Promise<void> {
  await fetch(`${API_BASE}/api/voice/conversation/abort`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ turn_id: turnId, thread_id: threadId }),
  });
}

export type SessionEventsSubscription = {
  stop: () => void;
};

export function subscribeSessionEvents(
  projectId: string,
  threadId: string,
  onEvent: DockStreamHandler,
): SessionEventsSubscription {
  const q = new URLSearchParams({ project_id: projectId, thread_id: threadId });
  const controller = new AbortController();
  const url = `${API_BASE}/api/agent/session/events?${q}`;

  void (async () => {
    try {
      const res = await fetch(url, { signal: controller.signal });
      if (!res.ok) return;
      await consumeSse(
        res,
        (raw) => {
          const type = String(raw.type || '');
          if (type === 'proactive' && typeof raw.text === 'string') {
            onEvent({ type: 'assistant_followup', text: raw.text, job_id: raw.job_id });
            return;
          }
          if (type === 'assistant_followup') {
            onEvent(raw);
            return;
          }
          if (type === 'job_update' || type === 'job_delete' || type === 'recommendation') {
            onEvent(raw);
          }
        },
        controller.signal,
      );
    } catch {
      /* aborted or network */
    }
  })();

  return {
    stop: () => controller.abort(),
  };
}

export function voiceContextToJson(ctx: VoiceContext): Record<string, unknown> {
  return {
    active_project_id: ctx.active_project_id,
    muted: ctx.muted,
    custom_fields: ctx.custom_fields,
    selected_node_ids: ctx.selected_node_ids,
    thread_id: ctx.thread_id,
  };
}

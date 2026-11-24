import { ConnectionState, Participant, Room, RoomEvent, Track } from 'livekit-client';

import type { VoiceSessionState } from './livekitService';
import { fetchLiveKitToken } from './livekitService';

export type VoiceContext = {
  active_project_id: string;
  muted: boolean;
  custom_fields: Record<string, string>;
  selected_node_ids: string[];
  thread_id: string;
};

/** Align WS host with the page so WebRTC/signal use the same loopback (127.0.0.1 vs localhost). */
export function normalizeLiveKitUrl(url: string): string {
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

export class VoiceSession {
  room: Room | null = null;
  private onState?: (s: VoiceSessionState) => void;
  private onDockEvent?: (ev: Record<string, unknown>) => void;
  private connectPromise: Promise<void> | null = null;
  private liveContext: VoiceContext | null = null;

  constructor(
    onState?: (s: VoiceSessionState) => void,
    onDockEvent?: (ev: Record<string, unknown>) => void,
  ) {
    this.onState = onState;
    this.onDockEvent = onDockEvent;
  }

  setDockEventHandler(handler?: (ev: Record<string, unknown>) => void) {
    this.onDockEvent = handler;
  }

  private emit(state: VoiceSessionState) {
    this.onState?.(state);
  }

  isReady(): boolean {
    return this.room?.state === ConnectionState.Connected;
  }

  getRoom(): Room | null {
    return this.room;
  }

  private async waitUntilConnected(room: Room, ms = 20_000): Promise<void> {
    if (room.state === ConnectionState.Connected) return;
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => {
        cleanup();
        reject(new Error('LiveKit did not reach Connected state in time'));
      }, ms);
      const onConnected = () => {
        cleanup();
        resolve();
      };
      const onDisconnected = () => {
        cleanup();
        reject(new Error('LiveKit disconnected while connecting'));
      };
      const cleanup = () => {
        clearTimeout(timer);
        room.off(RoomEvent.Connected, onConnected);
        room.off(RoomEvent.Disconnected, onDisconnected);
      };
      room.on(RoomEvent.Connected, onConnected);
      room.on(RoomEvent.Disconnected, onDisconnected);
    });
  }

  async connect(identity: string, roomName = 'me-mex'): Promise<void> {
    if (this.isReady()) return;
    if (this.connectPromise) {
      await this.connectPromise;
      return;
    }

    this.connectPromise = this.doConnect(identity, roomName);
    try {
      await this.connectPromise;
    } finally {
      this.connectPromise = null;
    }
  }

  private async doConnect(identity: string, roomName: string): Promise<void> {
    const { token, url: rawUrl } = await fetchLiveKitToken(roomName, identity);
    const url = normalizeLiveKitUrl(rawUrl);
    const room = new Room({ adaptiveStream: true });

    const attachAgentAudio = (track: {
      kind: Track.Kind;
      attach: (element?: HTMLMediaElement) => HTMLMediaElement;
    }) => {
      if (track.kind !== Track.Kind.Audio) return;
      let el = document.getElementById('agent-tts-audio') as HTMLAudioElement | null;
      if (!el) {
        el = track.attach() as HTMLAudioElement;
        el.id = 'agent-tts-audio';
        el.volume = 1;
        document.body.appendChild(el);
      } else {
        track.attach(el);
      }
      void room.startAudio().catch(() => undefined);
      void el.play().catch(() => undefined);
    };

    room.on(RoomEvent.TrackSubscribed, (track) => {
      attachAgentAudio(track);
    });
    room.on(RoomEvent.DataReceived, (payload) => {
      try {
        const msg = JSON.parse(new TextDecoder().decode(payload)) as Record<string, unknown>;
        const dockTypes = new Set([
          'dock_event',
          'dock_events',
          'turn_end',
          'turn_start',
          'stt_draft',
          'turn_aborted',
          'turn_reverted',
          'recommendation',
          'job_update',
          'job_delete',
          'proactive_reply',
          'assistant_followup',
          'awaiting_approval',
          'approval',
          'token',
          'custom',
        ]);
        if (dockTypes.has(String(msg.type))) {
          this.onDockEvent?.(msg);
        }
        if (msg.type === 'agent_reply' || msg.type === 'turn_end') {
          this.emit('Speaking');
        }
        if (msg.type === 'awaiting_approval') {
          this.emit('Awaiting approval');
        }
      } catch {
        /* ignore */
      }
    });
    room.on(RoomEvent.Disconnected, () => {
      this.room = null;
      this.liveContext = null;
      this.emit('Muted');
    });
    room.on(RoomEvent.ParticipantConnected, (p: Participant) => {
      if (p.identity === room.localParticipant.identity) return;
      const ctx = this.liveContext;
      if (ctx && this.isReady() && !ctx.muted) {
        void this.publishContextUpdate(ctx, false);
      }
    });

    try {
      this.emit('Thinking');
      await room.connect(url, token, { autoSubscribe: true });
      await this.waitUntilConnected(room);
      this.room = room;
      void room.startAudio().catch(() => undefined);
      this.emit('Listening');
    } catch (err) {
      await room.disconnect();
      this.room = null;
      this.emit('Muted');
      throw err;
    }
  }

  private async publishContextUpdate(ctx: VoiceContext, muted: boolean): Promise<void> {
    if (!this.room || !this.isReady()) {
      throw new Error('LiveKit room is not connected');
    }
    const payload = new TextEncoder().encode(
      JSON.stringify({
        type: 'context_update',
        muted,
        thread_id: ctx.thread_id,
        context_json: {
          active_project_id: ctx.active_project_id,
          muted,
          custom_fields: ctx.custom_fields,
          selected_node_ids: ctx.selected_node_ids,
        },
      }),
    );
    await this.room.localParticipant.publishData(payload, { reliable: true });
  }

  /** Update worker context without blocking the UI on data-channel ACK. */
  publishContextFireAndForget(ctx: VoiceContext): void {
    if (!this.room || !this.isReady()) return;
    void this.publishContextUpdate(ctx, ctx.muted).catch(() => undefined);
  }

  setLiveContext(ctx: VoiceContext | null): void {
    this.liveContext = ctx;
  }

  async setMicrophoneEnabled(enabled: boolean): Promise<void> {
    if (!this.room || !this.isReady()) {
      throw new Error('LiveKit room is not connected — mic cannot be published');
    }
    await this.room.localParticipant.setMicrophoneEnabled(enabled);
  }

  /** Mic + context for voice rail; context is sent async (see VoiceRail useEffect). */
  async applyMicMuted(muted: boolean, ctx: VoiceContext): Promise<void> {
    if (!this.room || !this.isReady()) {
      throw new Error('LiveKit room is not connected — mic cannot be published');
    }
    if (muted) {
      this.liveContext = null;
      await this.setMicrophoneEnabled(false);
    } else {
      this.liveContext = { ...ctx, muted: false };
      // Publish before opening mic when possible; never block UI on ACK.
      this.publishContextFireAndForget({ ...ctx, muted: false });
      await this.setMicrophoneEnabled(true);
    }
    this.emit(muted ? 'Muted' : 'Listening');
  }

  /** @deprecated Prefer applyMicMuted + publishContextFireAndForget from the rail. */
  async setMuted(muted: boolean, ctx: VoiceContext): Promise<void> {
    await this.applyMicMuted(muted, ctx);
    if (muted) {
      this.publishContextFireAndForget({ ...ctx, muted: true });
    }
  }

  async publishContext(ctx: VoiceContext): Promise<void> {
    if (!this.room || !this.isReady()) return;
    this.publishContextFireAndForget(ctx);
  }

  async sendAgentTurn(text: string, ctx: VoiceContext): Promise<void> {
    if (!this.room || !this.isReady()) return;
    await this.room.localParticipant.publishData(
      new TextEncoder().encode(
        JSON.stringify({ type: 'agent_turn', text, context_json: ctx }),
      ),
      { reliable: true },
    );
  }

  async sendCancelTurn(turnId: string): Promise<void> {
    if (!this.room || !this.isReady()) return;
    await this.room.localParticipant.publishData(
      new TextEncoder().encode(JSON.stringify({ type: 'cancel_turn', turn_id: turnId })),
      { reliable: true },
    );
  }

  async sendApproval(approvalId: string, action: 'approve' | 'cancel', ctx: VoiceContext) {
    if (!this.room || !this.isReady()) return;
    await this.room.localParticipant.publishData(
      new TextEncoder().encode(
        JSON.stringify({
          type: action === 'approve' ? 'approve' : 'cancel',
          approval_id: approvalId,
          context_json: {
            active_project_id: ctx.active_project_id,
            custom_fields: ctx.custom_fields,
          },
        }),
      ),
      { reliable: true },
    );
  }

  async disconnect(): Promise<void> {
    if (this.connectPromise) {
      await Promise.race([
        this.connectPromise.catch(() => undefined),
        new Promise<void>((r) => window.setTimeout(r, 400)),
      ]);
    }
    const room = this.room;
    this.room = null;
    this.liveContext = null;
    this.connectPromise = null;
    if (room) {
      void room.localParticipant.setMicrophoneEnabled(false).catch(() => undefined);
      await Promise.race([
        room.disconnect(),
        new Promise<void>((r) => window.setTimeout(r, 3_000)),
      ]);
    }
    this.emit('Muted');
  }
}

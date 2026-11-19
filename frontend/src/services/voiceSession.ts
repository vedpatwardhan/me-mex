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

    room.on(RoomEvent.TrackSubscribed, (track) => {
      if (track.kind === Track.Kind.Audio) {
        const el = track.attach();
        el.id = 'agent-tts-audio';
        document.body.appendChild(el);
      }
    });
    room.on(RoomEvent.DataReceived, (payload) => {
      try {
        const msg = JSON.parse(new TextDecoder().decode(payload)) as Record<string, unknown>;
        const dockTypes = new Set(['dock_event', 'dock_events', 'turn_end', 'turn_start']);
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

  async setMuted(muted: boolean, ctx: VoiceContext): Promise<void> {
    if (!this.room || !this.isReady()) {
      throw new Error('LiveKit room is not connected — mic cannot be published');
    }
    if (!muted) {
      this.liveContext = { ...ctx, muted: false };
      // Worker ignores mic audio until context_update sets muted=false.
      await this.publishContextUpdate(ctx, false);
      await this.room.localParticipant.setMicrophoneEnabled(true);
      window.setTimeout(() => {
        if (this.liveContext && this.isReady()) {
          void this.publishContextUpdate(this.liveContext, false);
        }
      }, 1500);
    } else {
      this.liveContext = null;
      await this.room.localParticipant.setMicrophoneEnabled(false);
      await this.publishContextUpdate(ctx, true);
    }
    this.emit(muted ? 'Muted' : 'Listening');
  }

  async publishContext(ctx: VoiceContext): Promise<void> {
    if (!this.room || !this.isReady()) return;
    await this.publishContextUpdate(ctx, ctx.muted);
  }

  async sendAgentTurn(text: string, ctx: VoiceContext) {
    if (!this.room || !this.isReady()) return;
    await this.room.localParticipant.publishData(
      new TextEncoder().encode(
        JSON.stringify({
          type: 'agent_turn',
          text,
          context_json: {
            active_project_id: ctx.active_project_id,
            muted: ctx.muted,
            custom_fields: ctx.custom_fields,
            selected_node_ids: ctx.selected_node_ids,
          },
        }),
      ),
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
      try {
        await this.connectPromise;
      } catch {
        /* connect failed */
      }
    }
    const room = this.room;
    this.room = null;
    if (room) {
      await room.localParticipant.setMicrophoneEnabled(false).catch(() => undefined);
      await room.disconnect();
    }
    this.emit('Muted');
  }
}

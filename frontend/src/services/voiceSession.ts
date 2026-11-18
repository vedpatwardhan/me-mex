import { Room, RoomEvent, Track } from 'livekit-client';

import type { VoiceSessionState } from './livekitService';
import { fetchLiveKitToken } from './livekitService';

export type VoiceContext = {
  active_project_id: string;
  muted: boolean;
  custom_fields: Record<string, string>;
  selected_node_ids: string[];
  thread_id: string;
};

export class VoiceSession {
  room: Room | null = null;
  private onState?: (s: VoiceSessionState) => void;

  constructor(onState?: (s: VoiceSessionState) => void) {
    this.onState = onState;
  }

  private emit(state: VoiceSessionState) {
    this.onState?.(state);
  }

  async connect(identity: string, roomName = 'me-mex'): Promise<void> {
    const { token, url } = await fetchLiveKitToken(roomName, identity);
    const room = new Room();
    this.room = room;
    room.on(RoomEvent.TrackSubscribed, (track) => {
      if (track.kind === Track.Kind.Audio) {
        const el = track.attach();
        el.id = 'agent-tts-audio';
        document.body.appendChild(el);
      }
    });
    room.on(RoomEvent.DataReceived, (payload) => {
      try {
        const msg = JSON.parse(new TextDecoder().decode(payload));
        if (msg.type === 'agent_reply') {
          this.emit('Speaking');
        }
        if (msg.type === 'awaiting_approval') {
          this.emit('Awaiting approval');
        }
      } catch {
        /* ignore */
      }
    });
    await room.connect(url, token);
    this.emit('Listening');
  }

  async setMuted(muted: boolean, ctx: VoiceContext): Promise<void> {
    if (!this.room) return;
    await this.room.localParticipant.setMicrophoneEnabled(!muted);
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
    this.emit(muted ? 'Muted' : 'Listening');
  }

  async publishContext(ctx: VoiceContext): Promise<void> {
    if (!this.room) return;
    const payload = new TextEncoder().encode(
      JSON.stringify({
        type: 'context_update',
        thread_id: ctx.thread_id,
        context_json: {
          active_project_id: ctx.active_project_id,
          muted: ctx.muted,
          custom_fields: ctx.custom_fields,
          selected_node_ids: ctx.selected_node_ids,
        },
      }),
    );
    await this.room.localParticipant.publishData(payload, { reliable: true });
  }

  async sendApproval(approvalId: string, action: 'approve' | 'cancel', ctx: VoiceContext) {
    if (!this.room) return;
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
    await this.room?.disconnect();
    this.room = null;
    this.emit('Muted');
  }
}

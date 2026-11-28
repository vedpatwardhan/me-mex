/** Voice rail UI states (HTTP voice path — no LiveKit / TTS). */
export type VoiceSessionState =
  | 'Muted'
  | 'Listening'
  | 'Transcribing'
  | 'Reviewing'
  | 'Thinking'
  | 'Processing'
  | 'Streaming'
  | 'Awaiting approval';

export type VoiceContext = {
  active_project_id: string;
  muted: boolean;
  custom_fields: Record<string, string>;
  selected_node_ids: string[];
  thread_id: string;
};

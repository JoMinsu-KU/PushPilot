/** Finite microphone input. A transcript is never plan approval or motion authority. */
export interface VoiceBinding {
  session_id: string;
  workspace_revision: number;
  map: { id: string; version: string; geometry_hash: string };
}
export interface VoiceTranscript {
  schema_version: 'pushpilot.voice-transcript.v1';
  capture_id: string;
  request_id: string;
  transcript_id: string;
  text: string;
  source: 'voice';
  audio_source: 'microphone';
  provider: 'meta';
  requires_confirmation: true;
  audio_retained: false;
  mission_submitted: false;
  binding: VoiceBinding;
  expires_in_seconds: number;
}
export type VoicePhase = 'idle' | 'requesting' | 'recording' | 'transcribing' | 'ready' | 'error';
export interface VoiceInputState {
  phase: VoicePhase;
  levels: number[];
  elapsed: number;
  text: string;
  transcript: VoiceTranscript | null;
  error: string;
}

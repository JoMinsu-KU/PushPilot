import type { VoiceBinding, VoiceInputState, VoiceTranscript } from '../../contracts/voice';
import { commandErrorMessage } from './commandError';
import { createRequestId } from './requestId';
import { startVoiceCapture, type VoiceRecorder } from './voiceCapture';

const empty = (): VoiceInputState => ({ phase: 'idle', levels: Array(40).fill(0), elapsed: 0, text: '', transcript: null, error: '' });
export const sameVoiceBinding = (a: VoiceBinding | null, b: VoiceBinding | null) => Boolean(a && b
  && a.session_id === b.session_id && a.workspace_revision === b.workspace_revision
  && a.map.id === b.map.id && a.map.version === b.map.version && a.map.geometry_hash === b.map.geometry_hash);

export function parseVoiceTranscript(value: unknown, binding: VoiceBinding, capture: string): VoiceTranscript {
  const v = value as VoiceTranscript | null;
  if (!v || v.schema_version !== 'pushpilot.voice-transcript.v1' || v.capture_id !== capture
    || typeof v.transcript_id !== 'string' || !/^[a-f0-9-]{36}$/i.test(v.transcript_id)
    || typeof v.request_id !== 'string' || !v.request_id || v.source !== 'voice' || v.audio_source !== 'microphone'
    || v.provider !== 'meta' || v.requires_confirmation !== true || v.mission_submitted !== false || v.audio_retained !== false
    || typeof v.text !== 'string' || !v.text.trim() || v.text.length > 2000 || v.text.includes('\0')
    || !v.binding?.map || !sameVoiceBinding(v.binding, binding)
    || !Number.isFinite(v.expires_in_seconds) || v.expires_in_seconds <= 0 || v.expires_in_seconds > 1800) {
    throw new Error('The voice result could not be matched to this recording and workspace. Record again.');
  }
  return v;
}

interface Context { binding: VoiceBinding | null; enabled: boolean; configured: boolean; secure: boolean }
interface Dependencies { capture?: typeof startVoiceCapture; fetch?: typeof fetch; now?: () => number; id?: () => string }

/** Finite, cancelable input only. It has no goal submission or robot endpoints. */
export class VoiceInputController {
  private state = empty();
  private context: Context = { binding: null, enabled: false, configured: false, secure: false };
  private listeners = new Set<() => void>();
  private generation = 0;
  private recorder: VoiceRecorder | null = null;
  private request: AbortController | null = null;
  private deadline: ReturnType<typeof setTimeout> | undefined;
  private expiry: ReturnType<typeof setTimeout> | undefined;
  private startedAt = 0;
  private acceptedUntil = 0;
  private readonly capture: typeof startVoiceCapture;
  private readonly fetcher: typeof fetch;
  private readonly now: () => number;
  private readonly id: () => string;
  constructor(deps: Dependencies = {}) {
    this.capture = deps.capture ?? startVoiceCapture;
    this.fetcher = deps.fetch ?? ((...args) => fetch(...args));
    this.now = deps.now ?? Date.now;
    this.id = deps.id ?? createRequestId;
  }
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private publish(patch: Partial<VoiceInputState>) { this.state = { ...this.state, ...patch }; this.listeners.forEach(listener => listener()); }
  setContext(context: Context) {
    const changed = this.context.binding && !sameVoiceBinding(this.context.binding, context.binding);
    this.context = context;
    if (changed || (!context.enabled || !context.configured || !context.secure) && ['requesting', 'recording', 'transcribing'].includes(this.state.phase)) this.cancel();
  }
  private clearTimers() { clearTimeout(this.deadline); clearTimeout(this.expiry); this.deadline = this.expiry = undefined; }
  private discard(transcript: VoiceTranscript | null) {
    if (!transcript) return;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 5000);
    try { void this.fetcher(`/api/v1/voice/transcriptions/${encodeURIComponent(transcript.transcript_id)}`,
      { method: 'DELETE', signal: controller.signal }).catch(() => {}).finally(() => clearTimeout(timer)); }
    catch { clearTimeout(timer); }
  }
  cancel = () => {
    this.generation++; this.clearTimers(); this.request?.abort(); this.request = null;
    this.recorder?.cancel(); this.recorder = null;
    this.discard(this.state.transcript); this.acceptedUntil = 0;
    this.publish(empty());
  };
  private fail(message: string) { this.cancel(); this.publish({ phase: 'error', error: message }); }
  start = async () => {
    if (['requesting', 'recording', 'transcribing'].includes(this.state.phase)) return;
    const context = this.context;
    if (!context.enabled || !context.binding) { this.fail('Voice input is available when the workspace is ready for a new goal.'); return; }
    if (!context.secure) { this.fail('Microphone access needs trusted HTTPS on this iPad. Use typed input until HTTPS is ready.'); return; }
    if (!context.configured) { this.fail('MUSE voice transcription is not configured. You can still type your goal.'); return; }
    this.cancel();
    const generation = this.generation;
    this.publish({ phase: 'requesting' });
    this.deadline = setTimeout(() => { if (generation === this.generation) this.fail('Microphone permission timed out. Tap the microphone to try again or use typed input.'); }, 30000);
    try {
      // Called directly from a user click; capture creates/resumes AudioContext before its first await.
      const recorder = await this.capture({
        onLevel: level => {
          if (generation !== this.generation || this.state.phase !== 'recording') return;
          this.publish({ levels: [...this.state.levels.slice(1), Math.min(1, Math.max(0, level))], elapsed: Math.min(20, (this.now() - this.startedAt) / 1000) });
        },
        onLimit: () => { if (generation === this.generation) void this.stop(); },
        onInterrupted: message => { if (generation === this.generation) this.fail(message); },
      });
      if (generation !== this.generation || !this.context.enabled || !this.context.configured || !this.context.secure || !sameVoiceBinding(context.binding, this.context.binding)) { recorder.cancel(); return; }
      clearTimeout(this.deadline);
      this.recorder = recorder; this.startedAt = this.now(); this.publish({ phase: 'recording' });
    } catch (error) {
      if (generation === this.generation) this.fail(error instanceof Error ? error.message : 'Microphone access failed. Use typed input or try again.');
    }
  };
  stop = async () => {
    if (this.state.phase !== 'recording' || !this.recorder || !this.context.binding) return;
    const generation = this.generation, binding = structuredClone(this.context.binding), recorder = this.recorder;
    this.publish({ phase: 'transcribing', levels: Array(40).fill(0) });
    try {
      const wav = await recorder.stop();
      if (this.recorder === recorder) this.recorder = null;
      if (generation !== this.generation || !this.context.enabled || !sameVoiceBinding(binding, this.context.binding)) return;
      const capture = this.id(), body = new FormData();
      body.append('file', wav, 'goal.wav'); body.append('expected_revision', String(binding.workspace_revision));
      body.append('capture_id', capture); body.append('audio_source', 'microphone');
      const request = new AbortController(); this.request = request;
      this.deadline = setTimeout(() => { if (generation === this.generation) this.fail('Voice recognition timed out. Record again or use typed input.'); }, 60000);
      const response = await this.fetcher('/api/v1/voice/transcriptions', { method: 'POST', body, signal: request.signal });
      const result: unknown = await response.json();
      if (generation !== this.generation) {
        // A completed response after cancellation is never displayed or accepted.
        try { this.discard(parseVoiceTranscript(result, binding, capture)); } catch { /* No usable candidate. */ }
        return;
      }
      if (!response.ok) throw new Error(commandErrorMessage(result, response.status));
      const transcript = parseVoiceTranscript(result, binding, capture);
      if (!this.context.enabled || !sameVoiceBinding(binding, this.context.binding)) { this.discard(transcript); return; }
      clearTimeout(this.deadline); this.request = null;
      this.acceptedUntil = this.now() + transcript.expires_in_seconds * 1000;
      this.expiry = setTimeout(() => { if (generation === this.generation) this.fail('This transcript expired. Record again or type your goal.'); }, transcript.expires_in_seconds * 1000);
      this.publish({ phase: 'ready', text: transcript.text, transcript, error: '' });
    } catch (error) {
      if (generation === this.generation) this.fail(error instanceof Error ? error.message : 'Voice recognition failed. No goal was submitted.');
    }
  };
  setText = (text: string) => { if (this.state.phase === 'ready') this.publish({ text: text.slice(0, 2000) }); };
  goalInput = () => {
    const { transcript, text } = this.state;
    if (!this.context.enabled || this.state.phase !== 'ready' || !transcript || !sameVoiceBinding(transcript.binding, this.context.binding)
      || this.now() >= this.acceptedUntil || !text.trim() || text.trim().length > 500) return null;
    return { text: text.trim(), source: 'voice' as const, provider: 'meta' as const, transcript_id: transcript.transcript_id, planning_mode: 'live' as const };
  };
}

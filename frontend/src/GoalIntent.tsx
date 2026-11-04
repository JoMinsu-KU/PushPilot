import type { VoiceInputState } from '../../contracts/voice';
import { Icon } from './Icons';

export function VoiceWaveform({ levels }: { levels: number[] }) {
  return <span className="voice-waveform" role="img" aria-label="Live microphone volume">
    {levels.map((level, index) => <i key={index} style={{ height: (6 + 42 * Math.min(1, Math.sqrt(Math.max(0, level)) * 2)) + 'px' }}/>)}</span>;
}
export function VoiceSpinner() { return <span className="voice-spinner" aria-hidden="true"/>; }

/** Accepted goals and unaccepted microphone transcripts remain distinct. */
export function GoalIntentBar({ query, onQuery, onVoice, voice, canRecord = true, onCancelVoice }: {
  query: string | null; source?: 'typed' | 'voice' | null;
  onQuery: () => void; onVoice: () => void;
  voice?: VoiceInputState; canRecord?: boolean; onCancelVoice?: () => void;
}) {
  const recording = voice?.phase === 'recording';
  const pending = voice?.phase === 'requesting' || voice?.phase === 'transcribing';
  const displayed = voice?.phase === 'ready' ? voice.text : voice?.phase === 'error' ? voice.error : query;
  return <div className={'goal-intent-bar glass-surface voice-' + (voice?.phase ?? 'idle')} role="group" aria-label="Goal input and original query">
    <button className={'goal-intent-mic' + (recording ? ' is-recording' : '')} onClick={onVoice}
      disabled={pending || !canRecord && !recording} aria-label={recording ? 'Finish recording and recognize speech' : voice?.phase === 'ready' ? 'Review recognized goal' : 'Record a voice goal'} aria-pressed={recording}>
      <Icon name="mic" size={22}/>
    </button>
    {recording ? <div className="voice-inline-recording"><VoiceWaveform levels={voice.levels}/><output>{Math.floor(voice.elapsed)}s / 20s</output><span className="voice-sr-only" role="status">Listening. Tap the microphone to finish.</span></div>
      : pending ? <div className="voice-inline-processing" role="status"><VoiceSpinner/><span>{voice.phase === 'requesting' ? 'Allow microphone access…' : 'Recognizing speech…'}</span></div>
        : <button className="goal-intent-query" onClick={onQuery} aria-label={voice?.phase === 'ready' ? 'Review the recognized goal before creating a plan' : query ? 'View or edit the mission goal' : 'Enter a mission goal'}>
          <span className={'goal-intent-text ' + (displayed ? '' : 'empty')}>{displayed || 'Tell PushPilot where to go.'}</span>
          <Icon name="chevron" className="goal-intent-chevron" size={18}/>
        </button>}
    {(recording || pending) && <button className="voice-inline-cancel" onClick={onCancelVoice} aria-label="Cancel voice input"><Icon name="close" size={18}/></button>}
  </div>;
}

export function VoiceInputOptions({ canEdit, onContinue, voice, onRecord, onStop, onCancel, onText, onUseGoal, busy = false, blockedReason }: {
  canEdit: boolean; onContinue: () => void; voice: VoiceInputState;
  onRecord: () => void; onStop: () => void; onCancel: () => void; onText: (text: string) => void;
  onUseGoal: () => void; busy?: boolean; blockedReason?: string;
}) {
  const recording = voice.phase === 'recording';
  const pending = voice.phase === 'requesting' || voice.phase === 'transcribing';
  const ready = voice.phase === 'ready';
  const valid = ready && voice.text.trim().length > 0 && voice.text.trim().length <= 500;
  return <section className="voice-input-options voice-connected" aria-label="Voice goal input">
    <div className="voice-input-heading"><span>MUSE · Voice input</span><strong>{recording ? 'Listening' : pending ? 'Processing' : ready ? 'Review transcript' : 'Tap to speak'}</strong></div>
    {ready ? <label className="voice-transcript-label" htmlFor="voice-transcript">Your goal<textarea id="voice-transcript" value={voice.text} onChange={event => onText(event.target.value)} disabled={!canEdit || busy} maxLength={2000} rows={3}/><small>{voice.text.length} / 500 characters for a goal</small></label>
      : <><button className={'voice-hold-button' + (recording ? ' is-recording' : '')} disabled={pending || !canEdit} onClick={recording ? onStop : onRecord} aria-label={recording ? 'Finish recording and recognize speech' : 'Record a voice goal'}>{pending ? <VoiceSpinner/> : <Icon name="mic" size={25}/>}<span>{recording ? 'Finish recording' : pending ? 'Recognizing…' : 'Tap to speak'}</span></button>
        {recording && <VoiceWaveform levels={voice.levels}/>}<h3>{recording ? 'Listening to your goal.' : pending ? 'Turning speech into words.' : 'A goal, in your own words.'}</h3>
        <p>{recording ? 'Tap the microphone when you finish. Recording ends after 20 seconds.' : pending ? 'Your microphone is released after recording. Wait for the transcription or cancel.' : 'Tap once to record, then tap again to finish. Review the words before creating a plan.'}</p></>}
    {voice.error && <p className="voice-error" role="alert">{voice.error}</p>}
    {!canEdit && !busy && <p className="voice-error">{blockedReason || 'Finish the current mission and prepare a new workspace before entering another goal.'}</p>}
    {ready && <p className="voice-confirmation-note">Edit any recognition mistakes. Creating a plan does not approve it or start the robot.</p>}
    <footer><div className="voice-secondary-actions"><button className="voice-text-fallback" onClick={onContinue}>{canEdit ? 'Type instead' : 'View original query'}</button>{(recording || pending || ready) && <button onClick={onCancel}>{ready ? 'Discard' : 'Cancel'}</button>}{ready && <button onClick={onRecord} disabled={!canEdit || busy}>Record again</button>}</div>
      {ready && <button className="primary-button" onClick={onUseGoal} disabled={!canEdit || !valid || busy}>{busy ? <><VoiceSpinner/>Creating a plan…</> : <>Create a plan<Icon name="arrow" size={17}/></>}</button>}</footer>
  </section>;
}

import { Icon } from './Icons';

/** The accepted request stays visible independently of the interpreted destination. */
export function GoalIntentBar({ query, onQuery, onVoice }: {
  query: string | null; source?: 'typed' | 'voice' | null;
  onQuery: () => void; onVoice: () => void;
}) {
  return <div className="goal-intent-bar glass-surface" role="group" aria-label="Goal input and original query">
    <button className="goal-intent-mic" onClick={onVoice} aria-label="Voice input options">
      <Icon name="mic" size={22}/>
    </button>
    <button className="goal-intent-query" onClick={onQuery} aria-label={query ? 'View or edit the mission goal' : 'Enter a mission goal'}>
      <span className={`goal-intent-text ${query ? '' : 'empty'}`}>{query ?? 'Tell PushPilot where to go.'}</span>
      <Icon name="chevron" className="goal-intent-chevron" size={18}/>
    </button>
  </div>;
}

/** A visible entry point, without requesting microphone permission or simulating capture. */
export function VoiceInputOptions({ canEdit, onContinue }: { canEdit: boolean; onContinue: () => void }) {
  return <section className="voice-input-options" aria-label="Voice input availability">
    <div className="voice-input-heading"><span>Voice input</span><strong>Not connected</strong></div>
    <button className="voice-hold-button" disabled aria-label="Hold to speak — not connected"><Icon name="mic" size={25}/><span>Hold to speak</span></button>
    <h3>A goal, in your own words.</h3>
    <p>Voice capture is not connected yet. You can enter your goal as text.</p>
    <div className="voice-input-guide"><span>When connected</span><ol><li><b>01</b><span>Hold and speak</span></li><li><b>02</b><span>Review the text</span></li><li><b>03</b><span>Create a plan</span></li></ol></div>
    <footer><span>Every new plan needs your approval.</span><button className="primary-button" onClick={onContinue}>{canEdit ? 'Type a goal' : 'View original query'}<Icon name="arrow" size={17}/></button></footer>
  </section>;
}

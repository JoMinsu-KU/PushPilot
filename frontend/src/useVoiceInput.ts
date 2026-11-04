import { useEffect, useRef, useSyncExternalStore } from 'react';
import type { VoiceBinding } from '../../contracts/voice';
import { VoiceInputController } from './voiceSession';

export function useVoiceInput(binding: VoiceBinding | null, enabled: boolean, configured: boolean) {
  const controller = useRef<VoiceInputController | null>(null);
  if (!controller.current) controller.current = new VoiceInputController();
  const voice = controller.current;
  const state = useSyncExternalStore(voice.subscribe, voice.getSnapshot, voice.getSnapshot);
  const key = JSON.stringify(binding);
  useEffect(() => {
    voice.setContext({ binding, enabled, configured, secure: globalThis.isSecureContext === true });
  }, [voice, key, enabled, configured]);
  useEffect(() => {
    const hidden = () => { if (document.visibilityState === 'hidden' && ['requesting', 'recording', 'transcribing'].includes(voice.getSnapshot().phase)) voice.cancel(); };
    const pagehide = () => voice.cancel();
    document.addEventListener('visibilitychange', hidden); window.addEventListener('pagehide', pagehide);
    return () => { document.removeEventListener('visibilitychange', hidden); window.removeEventListener('pagehide', pagehide); voice.cancel(); };
  }, [voice]);
  return { state, start: voice.start, stop: voice.stop, cancel: voice.cancel, setText: voice.setText, goalInput: voice.goalInput };
}

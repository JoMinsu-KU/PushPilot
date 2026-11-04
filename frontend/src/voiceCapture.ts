/** Finite, opt-in microphone capture. No speech recognition or provider access occurs here. */
export const VOICE_SAMPLE_RATE = 16_000;
export const VOICE_MIN_SECONDS = 0.2;
export const VOICE_MAX_SECONDS = 20;
export const VOICE_MAX_BYTES = 1_048_576;

export interface VoiceRecorder {
  stop(): Promise<Blob>;
  cancel(): void;
}

export interface VoiceCaptureOptions {
  onLevel: (level: number) => void;
  onLimit: () => void;
  onInterrupted: (message: string) => void;
}

/**
 * Streaming fractional-bin averaging: integrate piecewise-constant input samples
 * over each 16 kHz output interval. This is a bounded box low-pass resampler,
 * rather than dropping samples. It is intended for speech, not music mastering.
 * Chunk boundaries do not affect the result. Output storage is always 20 seconds.
 */
export class VoicePcmAccumulator {
  readonly inputSampleRate: number;
  private readonly samples = new Float32Array(VOICE_SAMPLE_RATE * VOICE_MAX_SECONDS);
  private readonly ratio: number;
  private readonly maxInputFrames: number;
  private inputFrames = 0;
  private outputFrames = 0;
  private integral = 0;

  constructor(inputSampleRate: number) {
    if (!Number.isFinite(inputSampleRate) || inputSampleRate < 8_000 || inputSampleRate > 192_000) {
      throw new Error('The microphone sample rate is not supported. Please use another audio device.');
    }
    this.inputSampleRate = inputSampleRate;
    this.ratio = inputSampleRate / VOICE_SAMPLE_RATE;
    this.maxInputFrames = Math.floor(inputSampleRate * VOICE_MAX_SECONDS);
  }

  append(input: Float32Array): boolean {
    const count = Math.min(input.length, this.maxInputFrames - this.inputFrames);
    for (let i = 0; i < count; i += 1) {
      const sample = Number.isFinite(input[i]) ? Math.max(-1, Math.min(1, input[i])) : 0;
      let position = this.inputFrames;
      const end = position + 1;
      while (position < end && this.outputFrames < this.samples.length) {
        const boundary = (this.outputFrames + 1) * this.ratio;
        const next = Math.min(end, boundary);
        this.integral += sample * (next - position);
        position = next;
        // Multiplication above keeps boundaries independent of chunking. The
        // tolerance covers only floating-point round-off at an exact boundary.
        if (position >= boundary - 1e-9) {
          this.samples[this.outputFrames++] = this.integral / this.ratio;
          this.integral = 0;
        }
      }
      this.inputFrames += 1;
    }
    return this.inputFrames >= this.maxInputFrames;
  }

  get durationSeconds(): number { return this.outputFrames / VOICE_SAMPLE_RATE; }

  clear(): void {
    this.samples.fill(0);
    this.inputFrames = 0; this.outputFrames = 0; this.integral = 0;
  }

  toWav(): Blob {
    if (this.durationSeconds < VOICE_MIN_SECONDS) {
      throw new Error('That recording was too short. Please speak for at least a moment and try again.');
    }
    const byteLength = 44 + this.outputFrames * 2;
    if (byteLength > VOICE_MAX_BYTES) throw new Error('The recording is too large. Please record a shorter goal.');
    const buffer = new ArrayBuffer(byteLength);
    const view = new DataView(buffer);
    const text = (offset: number, value: string) => {
      for (let i = 0; i < value.length; i += 1) view.setUint8(offset + i, value.charCodeAt(i));
    };
    text(0, 'RIFF'); view.setUint32(4, byteLength - 8, true); text(8, 'WAVE');
    text(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
    view.setUint16(22, 1, true); view.setUint32(24, VOICE_SAMPLE_RATE, true);
    view.setUint32(28, VOICE_SAMPLE_RATE * 2, true); view.setUint16(32, 2, true);
    view.setUint16(34, 16, true); text(36, 'data'); view.setUint32(40, this.outputFrames * 2, true);
    for (let i = 0; i < this.outputFrames; i += 1) {
      const sample = Math.max(-1, Math.min(1, this.samples[i]));
      view.setInt16(44 + i * 2, Math.round(sample * (sample < 0 ? 32_768 : 32_767)), true);
    }
    return new Blob([buffer], { type: 'audio/wav' });
  }
}

export async function startVoiceCapture(options: VoiceCaptureOptions): Promise<VoiceRecorder> {
  if (!window.isSecureContext) {
    throw new Error('Microphone access needs a trusted HTTPS connection on this iPad. You can still type your goal.');
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error('This browser cannot access a microphone. Please use Safari or type your goal.');
  }
  const AudioContextClass = window.AudioContext
    || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioContextClass) throw new Error('Audio recording is not supported in this browser. You can still type your goal.');

  // Both happen before the first await, while the microphone button's user
  // activation is still valid. Safari may otherwise keep the context suspended.
  const context = new AudioContextClass();
  const initialResume = context.resume().then(() => true, () => false);
  let stream: MediaStream | null = null;
  let source: MediaStreamAudioSourceNode | null = null;
  let processor: AudioWorkletNode | ScriptProcessorNode | null = null;
  let sink: GainNode | null = null;
  let closed = false;
  let stopping = false;
  let limitNotified = false;
  let wallTimer: ReturnType<typeof setTimeout> | undefined;
  let flushTimer: ReturnType<typeof setTimeout> | undefined;
  let stopPromise: Promise<Blob> | null = null;
  let resolveStop: ((blob: Blob) => void) | null = null;
  let rejectStop: ((error: Error) => void) | null = null;
  let accumulator: VoicePcmAccumulator | null = null;
  let requestStop: (() => Promise<Blob>) | null = null;
  const trackListeners: Array<[MediaStreamTrack, () => void]> = [];
  const notify = (callback: () => void) => { try { callback(); } catch { /* UI callback cannot retain the microphone. */ } };
  const cleanup = () => {
    if (closed) return;
    closed = true;
    clearTimeout(wallTimer); clearTimeout(flushTimer);
    context.removeEventListener('statechange', contextChanged);
    for (const [track, listener] of trackListeners) track.removeEventListener('ended', listener);
    for (const track of stream?.getTracks() || []) track.stop();
    if (processor && 'port' in processor) {
      processor.port.onmessage = null;
      processor.onprocessorerror = null;
      processor.port.postMessage({ type: 'cancel' });
      processor.port.close();
    } else if (processor) processor.onaudioprocess = null;
    source?.disconnect(); processor?.disconnect(); sink?.disconnect();
    void context.close().catch(() => undefined);
    accumulator?.clear();
    notify(() => options.onLevel(0));
  };
  const interrupted = (message: string) => {
    if (closed || stopping) return;
    cleanup();
    notify(() => options.onInterrupted(message));
  };
  const contextChanged = () => {
    if (!closed && !stopping && String(context.state) !== 'running') {
      interrupted('Microphone recording was interrupted. Please record your goal again.');
    }
  };

  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: { ideal: 1 }, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      video: false,
    });
    if (!await initialResume || context.state !== 'running') await context.resume();
    if (context.state !== 'running') throw new Error('Audio recording could not start. Tap the microphone to try again.');
    const pcm = new VoicePcmAccumulator(context.sampleRate);
    accumulator = pcm;
    const limit = () => {
      if (closed || stopping || limitNotified) return;
      limitNotified = true;
      notify(options.onLimit);
      // Stop even if the UI callback has not yet retrieved the finite result.
      // A later stop() receives the same promise; no second recording is made.
      void requestStop?.().catch(() => undefined);
    };
    const append = (samples: Float32Array) => {
      if (closed) return;
      const reachedLimit = pcm.append(samples);
      if (!stopping) {
        let squares = 0;
        for (let i = 0; i < samples.length; i += 1) squares += samples[i] * samples[i];
        const rms = samples.length ? Math.min(1, Math.sqrt(squares / samples.length)) : 0;
        notify(() => options.onLevel(Number.isFinite(rms) ? rms : 0));
      }
      if (reachedLimit) limit();
    };
    const finish = () => {
      if (closed) return;
      try {
        const blob = pcm.toWav();
        cleanup(); resolveStop?.(blob);
      } catch (error) {
        cleanup(); rejectStop?.(error instanceof Error ? error : new Error('The recording could not be encoded.'));
      }
    };

    source = context.createMediaStreamSource(stream);
    sink = context.createGain(); sink.gain.value = 0;
    // A silent, connected output keeps Safari's audio graph rendering without
    // playing microphone audio through the tablet's speaker.
    sink.connect(context.destination);
    if (context.audioWorklet && typeof AudioWorkletNode !== 'undefined') {
      try {
        let moduleTimer: ReturnType<typeof setTimeout> | undefined;
        try {
          await Promise.race([
            context.audioWorklet.addModule('/voice-recorder.worklet.js'),
            new Promise<never>((_, reject) => { moduleTimer = setTimeout(() => reject(new Error('Audio module unavailable.')), 2000); }),
          ]);
        } finally { clearTimeout(moduleTimer); }
        const worklet = new AudioWorkletNode(context, 'pushpilot-voice-recorder', {
          numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1],
          processorOptions: { maxFrames: Math.floor(context.sampleRate * VOICE_MAX_SECONDS) },
        });
        worklet.port.onmessage = (event: MessageEvent) => {
          if (closed) return;
          const data = event.data;
          if (data?.type === 'samples' && data.samples instanceof Float32Array && data.samples.length <= 4096) append(data.samples);
          else if (data?.type === 'limit') limit();
          else if (data?.type === 'stopped' && stopping) finish();
        };
        worklet.onprocessorerror = () => interrupted('The microphone audio processor stopped. Please record your goal again.');
        processor = worklet;
      } catch {
        // No source was connected to a worklet yet. Fallback cannot capture a
        // second copy of the audio or run alongside the failed processor.
        processor = null;
      }
    }
    if (!processor) {
      const channels = Math.max(1, Math.min(2, stream.getAudioTracks()[0]?.getSettings().channelCount || 1));
      const legacy = context.createScriptProcessor(2048, channels, 1);
      legacy.onaudioprocess = (event: AudioProcessingEvent) => {
        for (let c = 0; c < event.outputBuffer.numberOfChannels; c += 1) event.outputBuffer.getChannelData(c).fill(0);
        if (closed || stopping) return;
        const input = event.inputBuffer;
        const mono = new Float32Array(input.length);
        for (let c = 0; c < input.numberOfChannels; c += 1) {
          const channel = input.getChannelData(c);
          for (let i = 0; i < mono.length; i += 1) mono[i] += channel[i] / input.numberOfChannels;
        }
        append(mono);
      };
      processor = legacy;
    }
    if (context.state !== 'running' || stream.getAudioTracks().some((track) => track.readyState === 'ended')) {
      throw new Error('Microphone recording was interrupted. Please record your goal again.');
    }
    source.connect(processor); processor.connect(sink);
    for (const track of stream.getAudioTracks()) {
      const listener = () => interrupted('Microphone access ended. Please reconnect the microphone and record again.');
      track.addEventListener('ended', listener);
      trackListeners.push([track, listener]);
    }
    context.addEventListener('statechange', contextChanged);
    requestStop = () => {
        if (stopPromise) return stopPromise;
        if (closed) return Promise.reject(new Error('This recording is no longer available. Please record again.'));
        stopping = true;
        clearTimeout(wallTimer);
        stopPromise = new Promise<Blob>((resolve, reject) => { resolveStop = resolve; rejectStop = reject; });
        for (const track of stream?.getTracks() || []) track.stop();
        if (processor && 'port' in processor) {
          // An acknowledged flush includes the final, partial audio chunk.
          flushTimer = setTimeout(() => {
            cleanup(); rejectStop?.(new Error('The recording could not finish. Please record your goal again.'));
          }, 1500);
          processor.port.postMessage({ type: 'stop' });
        } else finish();
        return stopPromise;
    };
    wallTimer = setTimeout(limit, VOICE_MAX_SECONDS * 1000);

    return {
      stop: requestStop,
      cancel() {
        cleanup();
        rejectStop?.(new Error('Recording cancelled.'));
      },
    };
  } catch (error) {
    cleanup();
    if (error instanceof DOMException && error.name === 'NotAllowedError') {
      throw new Error('Microphone permission was denied. Allow microphone access in Safari settings, or type your goal.');
    }
    if (error instanceof DOMException && ['NotFoundError', 'NotReadableError', 'AbortError'].includes(error.name)) {
      throw new Error('The microphone is unavailable or in use. Please try again, or type your goal.');
    }
    throw error instanceof Error ? error : new Error('The microphone could not start. You can still type your goal.');
  }
}

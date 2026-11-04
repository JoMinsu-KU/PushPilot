/* Same-origin audio processor. No network, storage, or speech recognition. */
class PushPilotVoiceRecorder extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.maxFrames = Math.min(Math.floor(sampleRate * 20), options.processorOptions?.maxFrames || Math.floor(sampleRate * 20));
    this.frames = 0;
    this.batch = new Float32Array(2048);
    this.used = 0;
    this.active = true;
    this.limitSent = false;
    this.port.onmessage = (event) => {
      if (event.data?.type === 'stop') {
        this.active = false;
        this.flush();
        this.port.postMessage({ type: 'stopped' });
      } else if (event.data?.type === 'cancel') {
        this.active = false;
        this.used = 0;
      }
    };
  }

  flush() {
    if (!this.used) return;
    const samples = this.batch.slice(0, this.used);
    this.port.postMessage({ type: 'samples', samples }, [samples.buffer]);
    this.used = 0;
  }

  process(inputs, outputs) {
    for (const output of outputs) for (const channel of output) channel.fill(0);
    const channels = inputs[0];
    if (!this.active || !channels?.length) return true;
    const count = Math.min(channels[0].length, this.maxFrames - this.frames);
    for (let i = 0; i < count; i += 1) {
      let sample = 0;
      for (const channel of channels) sample += channel[i] / channels.length;
      this.batch[this.used++] = Number.isFinite(sample) ? sample : 0;
      this.frames += 1;
      if (this.used === this.batch.length) this.flush();
    }
    if (this.frames >= this.maxFrames && !this.limitSent) {
      this.active = false;
      this.limitSent = true;
      this.flush();
      this.port.postMessage({ type: 'limit' });
    }
    return true;
  }
}

registerProcessor('pushpilot-voice-recorder', PushPilotVoiceRecorder);

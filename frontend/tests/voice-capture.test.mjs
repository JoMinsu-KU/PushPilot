import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';
import { VoicePcmAccumulator, startVoiceCapture } from '../src/voiceCapture.ts';

const wav = async (capture) => {
  const blob = capture.toWav();
  const bytes = new Uint8Array(await blob.arrayBuffer());
  return { blob, bytes, view: new DataView(bytes.buffer), pcm: new Int16Array(bytes.buffer, 44) };
};

test('16 kHz PCM WAV has canonical mono header and preserves signed sample values', async () => {
  const capture = new VoicePcmAccumulator(16_000);
  const input = Float32Array.from({ length: 3200 }, (_, i) => [-1, -0.5, 0, 0.5, 1][i % 5]);
  capture.append(input);
  const { blob, bytes, view, pcm } = await wav(capture);
  assert.equal(blob.type, 'audio/wav'); assert.equal(blob.size, 6444);
  assert.equal(new TextDecoder().decode(bytes.slice(0, 4)), 'RIFF');
  assert.equal(new TextDecoder().decode(bytes.slice(8, 12)), 'WAVE');
  assert.equal(view.getUint32(4, true), blob.size - 8);
  assert.equal(view.getUint16(20, true), 1); assert.equal(view.getUint16(22, true), 1);
  assert.equal(view.getUint32(24, true), 16_000); assert.equal(view.getUint32(28, true), 32_000);
  assert.equal(view.getUint16(32, true), 2); assert.equal(view.getUint16(34, true), 16);
  assert.equal(view.getUint32(40, true), 6400);
  assert.deepEqual([...pcm.slice(0, 5)], [-32768, -16384, 0, 16384, 32767]);
});

test('fractional resampling is chunk independent at 44.1 kHz and averages input bins at 48 kHz', async () => {
  const input = Float32Array.from({ length: 44_100 }, (_, i) => 0.6 * Math.sin(2 * Math.PI * 440 * i / 44_100));
  const whole = new VoicePcmAccumulator(44_100), split = new VoicePcmAccumulator(44_100);
  whole.append(input);
  for (let i = 0; i < input.length; i += 137) split.append(input.subarray(i, i + 137));
  assert.equal(whole.durationSeconds, 1);
  assert.deepEqual((await wav(whole)).bytes, (await wav(split)).bytes);
  const averaged = new VoicePcmAccumulator(48_000);
  averaged.append(Float32Array.from({ length: 9600 }, (_, i) => [1, -1, 0.75][i % 3]));
  assert.equal(averaged.durationSeconds, 0.2);
  assert.ok((await wav(averaged)).pcm.every((value) => value === 8192));
});

test('capture storage is capped at 20 seconds and clips invalid amplitudes without malformed PCM', async () => {
  const capture = new VoicePcmAccumulator(16_000);
  assert.equal(capture.append(new Float32Array(320_000).fill(2)), true);
  assert.equal(capture.append(new Float32Array(10_000).fill(-1)), true);
  const { blob, pcm } = await wav(capture);
  assert.equal(capture.durationSeconds, 20); assert.equal(blob.size, 640_044);
  assert.ok(blob.size < 1_048_576); assert.ok(pcm.every((sample) => sample === 32767));
  capture.clear(); assert.equal(capture.durationSeconds, 0);
  assert.throws(() => capture.toWav(), /too short/);
  assert.throws(() => new VoicePcmAccumulator(NaN), /sample rate/);
  assert.throws(() => new VoicePcmAccumulator(500_000), /sample rate/);
  const short = new VoicePcmAccumulator(16_000); short.append(new Float32Array(3199));
  assert.throws(() => short.toWav(), /too short/);
});

test('same-origin worklet downmixes real channels, outputs silence, flushes tail and caps exactly once', async () => {
  let Processor;
  class WorkletBase {
    constructor() { this.messages = []; this.port = { postMessage: (message) => this.messages.push(message), onmessage: null }; }
  }
  const source = await readFile(new URL('../public/voice-recorder.worklet.js', import.meta.url), 'utf8');
  vm.runInNewContext(source, { AudioWorkletProcessor: WorkletBase, sampleRate: 16_000,
    registerProcessor: (name, Class) => { assert.equal(name, 'pushpilot-voice-recorder'); Processor = Class; }, Float32Array });
  const processor = new Processor({ processorOptions: { maxFrames: 256 } });
  const left = new Float32Array(128).fill(0.75), right = new Float32Array(128).fill(-0.25);
  const output = new Float32Array(128).fill(1);
  processor.process([[left, right]], [[output]]);
  assert.ok(output.every((sample) => sample === 0));
  processor.port.onmessage({ data: { type: 'stop' } });
  assert.equal(processor.messages[0].type, 'samples');
  assert.equal(processor.messages[0].samples.length, 128);
  assert.ok(processor.messages[0].samples.every((sample) => sample === 0.25));
  assert.equal(processor.messages[1].type, 'stopped');
  const bounded = new Processor({ processorOptions: { maxFrames: 256 } });
  for (let i = 0; i < 10; i += 1) bounded.process([[left, right]], [[output]]);
  assert.equal(bounded.messages.filter((message) => message.type === 'limit').length, 1);
  assert.equal(bounded.messages.filter((message) => message.type === 'samples').reduce((sum, message) => sum + message.samples.length, 0), 256);
});

class FakeNode extends EventTarget {
  disconnected = false;
  connect() {}
  disconnect() { this.disconnected = true; }
}
class FakeTrack extends EventTarget {
  stops = 0;
  stop() { this.stops += 1; }
  getSettings() { return { channelCount: 2 }; }
}
class FakeContext extends EventTarget {
  static instances = [];
  state = 'suspended'; sampleRate = 16_000; destination = {}; nodes = []; closed = false;
  constructor() { super(); FakeContext.instances.push(this); }
  resume() { this.state = 'running'; return Promise.resolve(); }
  close() { this.closed = true; this.state = 'closed'; return Promise.resolve(); }
  createMediaStreamSource() { const node = new FakeNode(); this.nodes.push(node); return node; }
  createGain() { const node = new FakeNode(); node.gain = { value: 1 }; this.nodes.push(node); return node; }
  createScriptProcessor() { const node = new FakeNode(); this.processor = node; this.nodes.push(node); return node; }
}
const withBrowser = async (body, getUserMedia, Context = FakeContext, Worklet = undefined) => {
  const descriptors = ['window', 'navigator', 'AudioWorkletNode'].map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]);
  const track = new FakeTrack();
  const stream = { getTracks: () => [track], getAudioTracks: () => [track] };
  Object.defineProperty(globalThis, 'window', { configurable: true, value: { isSecureContext: true, AudioContext: Context } });
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { mediaDevices: {
    getUserMedia: (...args) => {
      assert.equal(FakeContext.instances.at(-1).state, 'running', 'resume is called before permission starts');
      return getUserMedia ? getUserMedia(...args) : Promise.resolve(stream);
    },
  } } });
  Object.defineProperty(globalThis, 'AudioWorkletNode', { configurable: true, value: Worklet });
  try { await body(track, stream); } finally {
    for (const [key, descriptor] of descriptors) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key];
    }
  }
};
const callbacks = (events) => ({ onLevel: (value) => events.levels.push(value),
  onLimit: () => { events.limits += 1; }, onInterrupted: (message) => events.interruptions.push(message) });
const audioEvent = (frames = 2048) => ({ inputBuffer: { length: frames, numberOfChannels: 2,
  getChannelData: (channel) => new Float32Array(frames).fill(channel ? -0.25 : 0.75) },
  outputBuffer: { numberOfChannels: 1, getChannelData: () => new Float32Array(frames) } });

test('browser capture starts only on request, resumes before permission and cleans fallback stop/cancel/interruption', async () => {
  const events = { levels: [], limits: 0, interruptions: [] };
  await withBrowser(async (track) => {
    const capture = await startVoiceCapture(callbacks(events));
    const context = FakeContext.instances.at(-1);
    assert.equal(context.nodes[1].gain.value, 0);
    for (let i = 0; i < 2; i += 1) context.processor.onaudioprocess(audioEvent());
    assert.equal(events.levels[0], 0.25);
    const result = capture.stop(); assert.equal(result, capture.stop());
    const blob = await result; assert.equal(blob.type, 'audio/wav');
    assert.ok(track.stops > 0); assert.equal(context.closed, true);
    assert.ok(context.nodes.every((node) => node.disconnected));
    assert.equal(events.levels.at(-1), 0);
    capture.cancel();
  });
  await withBrowser(async (track) => {
    const capture = await startVoiceCapture(callbacks(events));
    capture.cancel(); assert.ok(track.stops > 0);
    await assert.rejects(capture.stop(), /no longer available/);
  });
  await withBrowser(async (track) => {
    const capture = await startVoiceCapture(callbacks(events));
    track.dispatchEvent(new Event('ended'));
    assert.equal(FakeContext.instances.at(-1).closed, true);
    assert.equal(events.interruptions.length, 1);
    await assert.rejects(capture.stop(), /no longer available/);
  });
});

test('permission failures and short recordings release the context and preserve actionable errors', async () => {
  const events = { levels: [], limits: 0, interruptions: [] };
  await withBrowser(async () => {
    await assert.rejects(startVoiceCapture(callbacks(events)), /permission was denied/);
    assert.equal(FakeContext.instances.at(-1).closed, true);
  }, () => Promise.reject(new DOMException('no', 'NotAllowedError')));
  await withBrowser(async (track) => {
    const capture = await startVoiceCapture(callbacks(events));
    await assert.rejects(capture.stop(), /too short/);
    assert.ok(track.stops > 0); assert.equal(FakeContext.instances.at(-1).closed, true);
  });
});

test('sample limit notifies once and automatically releases the microphone without a UI stop callback', async () => {
  const events = { levels: [], limits: 0, interruptions: [] };
  await withBrowser(async (track) => {
    const capture = await startVoiceCapture(callbacks(events));
    const context = FakeContext.instances.at(-1);
    const process = context.processor.onaudioprocess;
    for (let i = 0; i < 158; i += 1) process(audioEvent());
    assert.equal(events.limits, 1); assert.ok(track.stops > 0); assert.equal(context.closed, true);
    assert.equal((await capture.stop()).size, 640_044);
  });
});

test('worklet stop includes the acknowledged tail; failed module loading activates only the fallback', async () => {
  const events = { levels: [], limits: 0, interruptions: [] };
  class WorkletContext extends FakeContext {
    audioWorklet = { addModule: async (url) => { assert.equal(url, '/voice-recorder.worklet.js'); } };
  }
  class Worklet extends FakeNode {
    constructor(context) {
      super(); context.processor = this; context.nodes.push(this);
      this.port = { onmessage: null, close: () => { this.portClosed = true; }, postMessage: (message) => {
        if (message.type === 'stop') queueMicrotask(() => {
          this.port.onmessage?.({ data: { type: 'samples', samples: new Float32Array(128).fill(0.5) } });
          this.port.onmessage?.({ data: { type: 'stopped' } });
        });
      } };
    }
  }
  await withBrowser(async (track) => {
    const capture = await startVoiceCapture(callbacks(events));
    const context = FakeContext.instances.at(-1);
    context.processor.port.onmessage({ data: { type: 'samples', samples: new Float32Array(3200).fill(0.25) } });
    const result = await capture.stop();
    assert.equal(result.size, 44 + 3328 * 2);
    const samples = new Int16Array(await result.arrayBuffer(), 44);
    assert.equal(samples.at(-1), 16384, 'the final partial batch is retained');
    assert.ok(track.stops > 0); assert.equal(context.processor.portClosed, true);
    assert.equal(context.closed, true);
  }, undefined, WorkletContext, Worklet);
  class FailedModuleContext extends FakeContext {
    audioWorklet = { addModule: async () => { throw new Error('Unavailable'); } };
  }
  let created = 0;
  class UnusedWorklet { constructor() { created += 1; } }
  await withBrowser(async () => {
    const capture = await startVoiceCapture(callbacks(events));
    const context = FakeContext.instances.at(-1);
    assert.equal(typeof context.processor.onaudioprocess, 'function');
    assert.equal(created, 0);
    capture.cancel();
  }, undefined, FailedModuleContext, UnusedWorklet);
});

test('insecure origins never request permission and a suspended context reports one interruption', async () => {
  const events = { levels: [], limits: 0, interruptions: [] };
  let requested = false;
  await withBrowser(async () => {
    window.isSecureContext = false;
    await assert.rejects(startVoiceCapture(callbacks(events)), /trusted HTTPS/);
    assert.equal(requested, false);
  }, () => { requested = true; throw new Error('Unexpected permission request'); });
  await withBrowser(async (track) => {
    const capture = await startVoiceCapture(callbacks(events));
    const context = FakeContext.instances.at(-1);
    context.state = 'suspended'; context.dispatchEvent(new Event('statechange'));
    context.dispatchEvent(new Event('statechange'));
    assert.equal(events.interruptions.length, 1); assert.ok(track.stops > 0);
    await assert.rejects(capture.stop(), /no longer available/);
  });
});

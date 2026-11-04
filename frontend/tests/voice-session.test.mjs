import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';

// Compile the real controller without listening on a port or touching a device.
const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)), configFile: false,
  server: { middlewareMode: true, watch: null }, appType: 'custom' });
test.after(() => server.close());
const { VoiceInputController, parseVoiceTranscript, sameVoiceBinding } = await server.ssrLoadModule('/src/voiceSession.ts');

const captureId = '61afae02-905e-4867-99a4-d3aa566a0e26';
const transcriptId = 'b80a1750-2f6d-4b0b-87b3-824ef0e360cf';
const binding = () => ({ session_id: 'workspace-one', workspace_revision: 7,
  map: { id: 'toy-a3', version: '4', geometry_hash: 'map-hash-one' } });
const context = (update = {}) => ({ binding: binding(), enabled: true, configured: true, secure: true, ...update });
const transcript = (update = {}) => ({ schema_version: 'pushpilot.voice-transcript.v1', capture_id: captureId,
  transcript_id: transcriptId, request_id: 'meta-request-one', text: '피자집에서 빌라로 가 줘', source: 'voice',
  audio_source: 'microphone', provider: 'meta', requires_confirmation: true, mission_submitted: false,
  audio_retained: false, binding: binding(), expires_in_seconds: 1800, ...update });
const response = (body = transcript(), status = 200) => ({ ok: status >= 200 && status < 300, status,
  json: async () => body });
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
const setup = ({ capture, fetcher, now } = {}) => {
  const requests = [], captures = [];
  const recorder = { stops: 0, cancels: 0,
    stop() { this.stops += 1; return Promise.resolve(new Blob(['finite-wave'], { type: 'audio/wav' })); },
    cancel() { this.cancels += 1; } };
  const controller = new VoiceInputController({ id: () => captureId, now: now || (() => 1000),
    capture: (options) => { captures.push(options); return capture ? capture(options, recorder) : Promise.resolve(recorder); },
    fetch: async (url, init) => { requests.push({ url, init }); return fetcher ? fetcher(url, init) : response(); } });
  controller.setContext(context());
  return { controller, requests, captures, recorder };
};
const tick = () => new Promise((resolve) => setImmediate(resolve));

test('recording levels are measured input, stop posts one bounded multipart and ready remains an unsubmitted candidate', async () => {
  const { controller, requests, captures, recorder } = setup();
  try {
    assert.equal(controller.getSnapshot().phase, 'idle'); assert.equal(requests.length, 0);
    assert.equal(controller.goalInput(), null);
    await controller.start(); assert.equal(controller.getSnapshot().phase, 'recording');
    captures[0].onLevel(0.3); assert.equal(controller.getSnapshot().levels.at(-1), 0.3);
    assert.equal(controller.getSnapshot().levels.length, 40);
    await controller.start(); assert.equal(captures.length, 1, 'a second click cannot create parallel recording');
    await controller.stop(); assert.equal(recorder.stops, 1);
    assert.equal(requests.length, 1); assert.equal(requests[0].url, '/api/v1/voice/transcriptions');
    assert.equal(requests[0].init.method, 'POST');
    const form = requests[0].init.body;
    assert.ok(form instanceof FormData); assert.equal(form.get('file').name, 'goal.wav');
    assert.equal(form.get('file').type, 'audio/wav'); assert.equal(form.get('file').size, 11);
    assert.equal(form.get('capture_id'), captureId); assert.equal(form.get('expected_revision'), '7');
    assert.equal(form.get('audio_source'), 'microphone');
    assert.deepEqual([...form.keys()].sort(), ['audio_source', 'capture_id', 'expected_revision', 'file']);
    assert.equal(controller.getSnapshot().phase, 'ready');
    assert.equal(controller.getSnapshot().text, transcript().text, 'original-language text is preserved');
    assert.equal(controller.getSnapshot().transcript.text, transcript().text);
    assert.deepEqual(controller.goalInput(), { text: transcript().text, source: 'voice', provider: 'meta',
      transcript_id: transcriptId, planning_mode: 'live' });
    assert.ok(requests.every(({ url }) => !/goal|plan|physical|robot/.test(url)), 'recognition never submits or approves a goal');
  } finally { controller.cancel(); }
});

test('strict response binding rejects mismatched, invented or malformed candidates', () => {
  assert.equal(parseVoiceTranscript(transcript(), binding(), captureId).text, transcript().text);
  assert.equal(sameVoiceBinding(binding(), binding()), true);
  assert.equal(sameVoiceBinding(null, binding()), false);
  for (const change of [
    { capture_id: 'another-capture' }, { schema_version: 'different' }, { source: 'demo' }, { provider: 'mock' },
    { audio_source: 'recorded_upload' }, { requires_confirmation: false }, { mission_submitted: true },
    { audio_retained: true }, { transcript_id: 'not-an-id' }, { request_id: '' }, { text: '' },
    { text: 'a\0b' }, { text: 'x'.repeat(2001) }, { expires_in_seconds: 0 }, { expires_in_seconds: 1801 },
    { expires_in_seconds: NaN }, { binding: { ...binding(), session_id: 'other' } },
    { binding: { ...binding(), workspace_revision: 8 } },
    ...['id', 'version', 'geometry_hash'].map((key) => ({ binding: { ...binding(), map: { ...binding().map, [key]: 'other' } } })),
  ]) assert.throws(() => parseVoiceTranscript(transcript(change), binding(), captureId), /could not be matched/);
});

test('cancelling pending permission cleans the late recorder and cannot resurrect recording or errors', async () => {
  const permission = deferred();
  const { controller, requests, recorder } = setup({ capture: () => permission.promise });
  const started = controller.start();
  assert.equal(controller.getSnapshot().phase, 'requesting');
  controller.cancel(); permission.resolve(recorder); await started;
  assert.equal(recorder.cancels, 1); assert.equal(controller.getSnapshot().phase, 'idle');
  assert.equal(requests.length, 0); assert.equal(controller.goalInput(), null);
  const failedPermission = deferred();
  const next = setup({ capture: () => failedPermission.promise });
  const pending = next.controller.start(); next.controller.cancel(); failedPermission.reject(new Error('Late denial'));
  await pending; assert.equal(next.controller.getSnapshot().phase, 'idle');
});

test('cancelled or superseded ASR results are discarded and cannot replace a newer capture', async () => {
  const upload = deferred();
  const { controller, requests } = setup({ fetcher: (url, init) => init.method === 'POST' ? upload.promise : response({}) });
  await controller.start(); const stopped = controller.stop(); await tick();
  const signal = requests[0].init.signal;
  assert.equal(controller.getSnapshot().phase, 'transcribing');
  controller.cancel(); assert.equal(signal.aborted, true);
  await controller.start(); assert.equal(controller.getSnapshot().phase, 'recording');
  upload.resolve(response()); await stopped;
  assert.equal(controller.getSnapshot().phase, 'recording', 'a late result cannot replace a new recording');
  assert.equal(controller.goalInput(), null);
  assert.equal(requests[1].url, `/api/v1/voice/transcriptions/${transcriptId}`);
  assert.equal(requests[1].init.method, 'DELETE'); controller.cancel();
});

test('every workspace identity component invalidates requesting, recording and ready results', async () => {
  for (const update of [{ session_id: 'other' }, { workspace_revision: 8 },
    ...['id', 'version', 'geometry_hash'].map((key) => ({ map: { ...binding().map, [key]: 'other' } }))]) {
    const { controller, recorder } = setup();
    await controller.start();
    controller.setContext(context({ binding: { ...binding(), ...update } }));
    assert.equal(recorder.cancels, 1); assert.equal(controller.getSnapshot().phase, 'idle');
    assert.equal(controller.goalInput(), null); controller.cancel();
  }
  const permission = deferred(), pending = setup({ capture: () => permission.promise });
  const started = pending.controller.start(); pending.controller.setContext(context({ enabled: false }));
  permission.resolve(pending.recorder); await started;
  assert.equal(pending.recorder.cancels, 1); assert.equal(pending.controller.getSnapshot().phase, 'idle');
  const ready = setup(); await ready.controller.start(); await ready.controller.stop();
  ready.controller.setContext(context({ binding: { ...binding(), workspace_revision: 8 } }));
  assert.equal(ready.controller.getSnapshot().phase, 'idle'); assert.equal(ready.controller.goalInput(), null);
  assert.ok(ready.requests.some(({ init }) => init.method === 'DELETE')); ready.controller.cancel();
});

test('cancel during final audio flush cancels that recorder immediately and never uploads the eventual WAV', async () => {
  const flush = deferred(); const { controller, recorder, requests } = setup();
  recorder.stop = () => flush.promise;
  await controller.start(); const stopped = controller.stop();
  controller.cancel(); assert.equal(recorder.cancels, 1, 'the recorder must remain reachable until its stop finishes');
  flush.resolve(new Blob(['wave'], { type: 'audio/wav' })); await stopped;
  assert.equal(requests.length, 0); assert.equal(controller.getSnapshot().phase, 'idle');
});

test('recording limit stops once, edits preserve original transcript, and goalInput has exact explicit acceptance shape', async () => {
  const { controller, captures, recorder } = setup();
  try {
    controller.setText('ignored before ready'); assert.equal(controller.getSnapshot().text, '');
    await controller.start(); captures[0].onLimit(); captures[0].onLimit(); await tick();
    assert.equal(recorder.stops, 1); assert.equal(controller.getSnapshot().phase, 'ready');
    controller.setText('  Push the car to Villa.  ');
    assert.equal(controller.getSnapshot().transcript.text, transcript().text);
    assert.deepEqual(controller.goalInput(), { text: 'Push the car to Villa.', source: 'voice', provider: 'meta',
      transcript_id: transcriptId, planning_mode: 'live' });
    controller.setText('x'.repeat(2500)); assert.equal(controller.getSnapshot().text.length, 2000);
    assert.equal(controller.goalInput(), null, 'overlong accepted goal is not silently shortened');
    controller.setText(' '.repeat(10)); assert.equal(controller.goalInput(), null);
    controller.setText('x'.repeat(500)); assert.equal(controller.goalInput().text.length, 500);
    controller.setContext(context({ enabled: false })); assert.equal(controller.goalInput(), null);
  } finally { controller.cancel(); }
});

test('transcription timeout aborts, rejects late success and leaves typed input with no invented transcript', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const upload = deferred();
  const { controller, requests } = setup({ fetcher: (url, init) => init.method === 'POST' ? upload.promise : response({}) });
  await controller.start(); const stopped = controller.stop(); await tick();
  t.mock.timers.tick(60_000);
  assert.equal(controller.getSnapshot().phase, 'error'); assert.match(controller.getSnapshot().error, /timed out/);
  assert.equal(requests[0].init.signal.aborted, true); assert.equal(controller.goalInput(), null);
  upload.resolve(response()); await stopped;
  assert.equal(controller.getSnapshot().phase, 'error'); assert.equal(controller.getSnapshot().transcript, null);
  controller.cancel(); t.mock.timers.reset();
});

test('permission timeout cannot turn a late granted microphone into a new recording', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const permission = deferred();
  const { controller, recorder, requests } = setup({ capture: () => permission.promise });
  const started = controller.start();
  t.mock.timers.tick(30_000);
  assert.equal(controller.getSnapshot().phase, 'error'); assert.match(controller.getSnapshot().error, /permission timed out/);
  permission.resolve(recorder); await started;
  assert.equal(recorder.cancels, 1); assert.equal(controller.getSnapshot().phase, 'error');
  assert.equal(requests.length, 0); assert.equal(controller.goalInput(), null);
  controller.cancel(); t.mock.timers.reset();
});

test('loss of transcription configuration or secure-context capability cancels an active recording', async () => {
  for (const update of [{ configured: false }, { secure: false }]) {
    const { controller, recorder, requests } = setup();
    await controller.start(); controller.setContext(context(update));
    assert.equal(recorder.cancels, 1); assert.equal(controller.getSnapshot().phase, 'idle');
    await controller.stop(); assert.equal(requests.length, 0); controller.cancel();
    const permission = deferred(), pending = setup({ capture: () => permission.promise });
    const started = pending.controller.start(); pending.controller.setContext(context(update));
    permission.resolve(pending.recorder); await started;
    assert.equal(pending.recorder.cancels, 1); assert.equal(pending.controller.getSnapshot().phase, 'idle');
  }
});

test('transcript expiry, rerecord and unmount-style cancellation retire the old candidate', async (t) => {
  let now = 1000;
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const { controller, requests, captures } = setup({ now: () => now,
    fetcher: (url, init) => response(init.method === 'POST' ? transcript({ expires_in_seconds: 2 }) : {}) });
  await controller.start(); await controller.stop(); now = 3000;
  assert.equal(controller.goalInput(), null, 'acceptance checks time independently of the timer');
  t.mock.timers.tick(2000); assert.equal(controller.getSnapshot().phase, 'error');
  assert.match(controller.getSnapshot().error, /expired/);
  await controller.start(); assert.equal(captures.length, 2);
  assert.equal(controller.getSnapshot().phase, 'recording');
  controller.cancel(); assert.equal(controller.getSnapshot().phase, 'idle');
  assert.ok(requests.some(({ init }) => init.method === 'DELETE')); t.mock.timers.reset();
});

test('capture and provider errors stay explicit, and insecure, unavailable or unconfigured contexts never capture', async () => {
  for (const update of [{ enabled: false }, { binding: null }, { configured: false }, { secure: false }]) {
    const { controller, captures, requests } = setup(); controller.setContext(context(update));
    await controller.start(); assert.equal(captures.length, 0); assert.equal(requests.length, 0);
    assert.equal(controller.getSnapshot().phase, 'error'); assert.equal(controller.goalInput(), null); controller.cancel();
  }
  const denied = setup({ capture: () => Promise.reject(new Error('Permission denied')) });
  await denied.controller.start(); assert.equal(denied.controller.getSnapshot().phase, 'error');
  assert.equal(denied.controller.getSnapshot().transcript, null); denied.controller.cancel();
  const provider = setup({ fetcher: () => response({ detail: { code: 'VOICE_UNAVAILABLE', message: 'Provider access failed.' } }, 503) });
  await provider.controller.start(); await provider.controller.stop();
  assert.match(provider.controller.getSnapshot().error, /VOICE_UNAVAILABLE: Provider access failed/);
  assert.equal(provider.controller.getSnapshot().transcript, null); assert.equal(provider.controller.goalInput(), null);
  assert.equal(provider.requests.length, 1); provider.controller.cancel();
});

test('the React hook cancels active capture on hidden pages and removes its page lifecycle listeners on unmount', async () => {
  const source = await readFile(new URL('../src/useVoiceInput.ts', import.meta.url), 'utf8');
  assert.match(source, /visibilityState === 'hidden'/);
  assert.match(source, /\['requesting', 'recording', 'transcribing'\]/);
  assert.match(source, /document\.addEventListener\('visibilitychange', hidden\)/);
  assert.match(source, /window\.addEventListener\('pagehide', pagehide\)/);
  assert.match(source, /document\.removeEventListener\('visibilitychange', hidden\)/);
  assert.match(source, /window\.removeEventListener\('pagehide', pagehide\); voice\.cancel\(\)/);
});

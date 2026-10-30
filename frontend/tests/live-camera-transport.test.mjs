import assert from 'node:assert/strict';
import test from 'node:test';
import { decodeLiveFrame, fetchLiveSnapshot, previewRetryDelay, withPreviewDeadline } from '../src/liveCameraTransport.ts';
import { liveFrameFresh } from '../src/liveCamera.ts';

const lifetime = () => new AbortController();
const pending = () => new Promise(() => {});
const frame = { id: 'native', image_url: '/api/v1/live-camera/frames/native/image', width: 1920, height: 1080, age_ms: 100 };
const snapshot = { schema_version: 'pushpilot.live-camera.v1', enabled: true, state: 'live', frame };
const reply = () => ({ ok: true, json: async () => snapshot });
const fakeImage = (decode = async () => {}) => ({
  src: '', naturalWidth: 1920, naturalHeight: 1080, removed: false, decode,
  removeAttribute(name) { assert.equal(name, 'src'); this.src = ''; this.removed = true; },
});

test('a hung status request is aborted and a subsequent request recovers without reloading', async () => {
  let requestSignal;
  const controller = lifetime();
  await assert.rejects(fetchLiveSnapshot(controller.signal, { timeoutMs: 15,
    fetcher: async (url, options) => {
      assert.equal(url, '/api/v1/live-camera'); assert.equal(options.cache, 'no-store');
      requestSignal = options.signal; return pending();
    },
  }), { name: 'AbortError' });
  assert.equal(requestSignal.aborted, true);
  assert.equal(controller.signal.aborted, false, 'timeout is local to one request');
  assert.equal(await fetchLiveSnapshot(controller.signal, { fetcher: async () => reply() }), snapshot);
});

test('the status deadline also bounds a stalled JSON body', async () => {
  await assert.rejects(fetchLiveSnapshot(lifetime().signal, { timeoutMs: 15,
    fetcher: async () => ({ ok: true, json: pending }),
  }), { name: 'AbortError' });
});

test('HTTP errors and incompatible metadata cannot become a decoded view', async () => {
  await assert.rejects(fetchLiveSnapshot(lifetime().signal, { fetcher: async () => ({ ok: false }) }), /unavailable/);
  await assert.rejects(fetchLiveSnapshot(lifetime().signal, { fetcher: async () => ({ ok: true, json: async () => ({}) }) }), /Invalid/);
});

test('an already cancelled poll never opens a request or starts image decoding', async () => {
  const controller = lifetime(); controller.abort();
  let calls = 0;
  await assert.rejects(fetchLiveSnapshot(controller.signal, { fetcher: async () => { calls++; return reply(); } }), { name: 'AbortError' });
  const image = fakeImage(async () => { calls++; });
  await assert.rejects(decodeLiveFrame(frame, controller.signal, { createImage: () => image }), { name: 'AbortError' });
  assert.equal(calls, 0); assert.equal(image.removed, true);
});

test('tablet wake or component cleanup can cancel a pending request immediately', async () => {
  const controller = lifetime(); let requestSignal;
  const work = fetchLiveSnapshot(controller.signal, { fetcher: async (_url, options) => {
    requestSignal = options.signal; return pending();
  } });
  controller.abort();
  await assert.rejects(work, { name: 'AbortError' });
  assert.equal(requestSignal.aborted, true);
});

test('a response that ignores cancellation and arrives late cannot satisfy the timed-out request', async () => {
  let resolve;
  const work = withPreviewDeadline(() => new Promise(done => { resolve = done; }), lifetime().signal, 15);
  await assert.rejects(work, { name: 'AbortError' });
  resolve(snapshot);
  await assert.rejects(work, { name: 'AbortError' });
});

test('successful decoding keeps the exact native URL and dimensions without re-encoding', async () => {
  const image = fakeImage();
  await decodeLiveFrame(frame, lifetime().signal, { createImage: () => image });
  assert.equal(image.src, frame.image_url); assert.equal(image.removed, false);
});

test('expired preloads are cancelled rather than accumulating hidden downloads', async () => {
  const image = fakeImage(pending);
  await assert.rejects(decodeLiveFrame(frame, lifetime().signal, { createImage: () => image, timeoutMs: 15 }), { name: 'AbortError' });
  assert.equal(image.removed, true);
  const next = fakeImage();
  await decodeLiveFrame(frame, lifetime().signal, { createImage: () => next });
  assert.equal(next.src, frame.image_url);
});

test('cleanup cancels an in-flight image and dimension/decode failures remain failures', async () => {
  const controller = lifetime(); const image = fakeImage(pending);
  const work = decodeLiveFrame(frame, controller.signal, { createImage: () => image });
  controller.abort(); await assert.rejects(work, { name: 'AbortError' });
  assert.equal(image.removed, true);
  for (const bad of [ { ...fakeImage(), naturalWidth: 1280 }, fakeImage(async () => { throw new Error('Corrupt JPEG'); }) ]) {
    await assert.rejects(decodeLiveFrame(frame, lifetime().signal, { createImage: () => bad }));
    assert.equal(bad.removed, true);
  }
});

test('recovery never renews old pixels or relaxes the existing 1500 ms freshness bound', () => {
  assert.equal(liveFrameFresh(snapshot, 0, 1400), true);
  assert.equal(liveFrameFresh(snapshot, 0, 1401), false);
  assert.deepEqual([1, 2, 3, 4, 10].map(previewRetryDelay), [125, 250, 500, 1000, 1000]);
});

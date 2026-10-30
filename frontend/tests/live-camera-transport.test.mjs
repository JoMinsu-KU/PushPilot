import assert from 'node:assert/strict';
import test from 'node:test';
import { createPreviewResources, decodeLiveFrame as decodeNative, fetchLiveSnapshot, PREVIEW_INTERVAL_MS, previewRetryDelay, withPreviewDeadline } from '../src/liveCameraTransport.ts';
import { liveFrameFresh } from '../src/liveCamera.ts';

const lifetime = () => new AbortController();
const pending = () => new Promise(() => {});
const frame = { id: 'native', image_url: '/api/v1/live-camera/frames/native/image', width: 1920, height: 1080, age_ms: 100 };
const snapshot = { schema_version: 'pushpilot.live-camera.v1', enabled: true, state: 'live', frame };
const reply = () => ({ ok: true, json: async () => snapshot });
const jpeg = new Blob([new Uint8Array([255, 216, 255, 217])], { type: 'image/jpeg' });
const jpegReply = () => ({ ok: true, headers: new Headers({ 'content-type': 'image/jpeg' }), blob: async () => jpeg });
const decodeLiveFrame = (frame, signal, options = {}) => decodeNative(frame, signal, {
  fetcher: async () => jpegReply(), createUrl: () => 'blob:native', revokeUrl: () => {}, ...options,
});
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

test('downloaded original bytes are shared by decoder and display with exactly one fetch', async () => {
  const image = fakeImage();
  let fetches = 0, revoked = 0;
  const resource = await decodeLiveFrame(frame, lifetime().signal, { createImage: () => image,
    fetcher: async (url) => { assert.equal(url, frame.image_url); fetches++; return jpegReply(); },
    createUrl: blob => { assert.equal(blob, jpeg); return 'blob:exact-original'; }, revokeUrl: () => revoked++,
  });
  assert.equal(image.src, resource.url); assert.equal(fetches, 1); assert.equal(image.removed, false);
  resource.dispose(); resource.dispose(); assert.equal(revoked, 1);
});

test('expired preloads are cancelled rather than accumulating hidden downloads', async () => {
  const image = fakeImage(pending);
  await assert.rejects(decodeLiveFrame(frame, lifetime().signal, { createImage: () => image, timeoutMs: 15 }), { name: 'AbortError' });
  assert.equal(image.removed, true);
  const next = fakeImage();
  await decodeLiveFrame(frame, lifetime().signal, { createImage: () => next });
  assert.equal(next.src, 'blob:native');
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

test('expired or invalid JPEG responses cannot become display resources', async () => {
  for (const response of [{ ...jpegReply(), ok: false }, { ...jpegReply(), headers: new Headers({ 'content-type': 'text/html' }) }]) {
    await assert.rejects(decodeLiveFrame(frame, lifetime().signal, { createImage: fakeImage, fetcher: async () => response }));
  }
  let created = 0, resolve;
  const work = decodeLiveFrame(frame, lifetime().signal, { createImage: fakeImage, timeoutMs: 15,
    fetcher: async () => ({ ...jpegReply(), blob: () => new Promise(done => { resolve = done; }) }),
    createUrl: () => { created++; return 'blob:late'; },
  });
  await assert.rejects(work, { name: 'AbortError' }); resolve(jpeg);
  await new Promise(done => setImmediate(done)); assert.equal(created, 0);
});

test('blob lifetime retains the displayed image through download and releases it after commit', () => {
  const resources = createPreviewResources(); const freed = [];
  resources.add({ url: 'first', dispose: () => freed.push('first') }); resources.committed('first');
  resources.add({ url: 'second', dispose: () => freed.push('second') }); assert.deepEqual(freed, []);
  resources.committed('first'); assert.deepEqual(freed, [], 'an older passive effect cannot release a newer pending frame');
  resources.committed('second'); assert.deepEqual(freed, ['first']);
  resources.dispose(); resources.dispose(); assert.deepEqual(freed, ['first', 'second']);
  assert.equal(PREVIEW_INTERVAL_MS, 250);
});

test('recovery never renews old pixels or relaxes the existing 1500 ms freshness bound', () => {
  assert.equal(liveFrameFresh(snapshot, 0, 1400), true);
  assert.equal(liveFrameFresh(snapshot, 0, 1401), false);
  assert.deepEqual([1, 2, 3, 4, 10].map(previewRetryDelay), [125, 250, 500, 1000, 1000]);
});

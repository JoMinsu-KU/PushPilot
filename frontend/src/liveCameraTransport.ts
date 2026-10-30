import type { LiveCameraSnapshot } from '../../contracts/live-camera';

/** Bound both the HTTP response and its body; a stalled request cannot stop preview polling. */
export async function withPreviewDeadline<T>(operation: (signal: AbortSignal) => Promise<T>,
  lifetime: AbortSignal, timeoutMs: number): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  let rejectAbort: (() => void) | undefined;
  const aborted = new Promise<never>((_, reject) => {
    rejectAbort = () => reject(new DOMException('Camera preview request cancelled.', 'AbortError'));
    controller.signal.addEventListener('abort', rejectAbort, { once: true });
  });
  lifetime.addEventListener('abort', abort, { once: true });
  const deadline = setTimeout(abort, timeoutMs);
  try {
    if (lifetime.aborted) abort();
    return await Promise.race([aborted, controller.signal.aborted ? aborted : operation(controller.signal)]);
  } finally {
    clearTimeout(deadline);
    lifetime.removeEventListener('abort', abort);
    if (rejectAbort) controller.signal.removeEventListener('abort', rejectAbort);
  }
}

export async function fetchLiveSnapshot(signal: AbortSignal,
  { fetcher = fetch, timeoutMs = 1000 }: { fetcher?: typeof fetch; timeoutMs?: number } = {}): Promise<LiveCameraSnapshot> {
  return withPreviewDeadline(async requestSignal => {
    const response = await fetcher('/api/v1/live-camera', { cache: 'no-store', signal: requestSignal });
    if (!response.ok) throw new Error('Live camera status is unavailable.');
    const snapshot = await response.json() as LiveCameraSnapshot;
    if (snapshot.schema_version !== 'pushpilot.live-camera.v1') throw new Error('Invalid live camera status.');
    return snapshot;
  }, signal, timeoutMs);
}

export async function decodeLiveFrame(frame: NonNullable<LiveCameraSnapshot['frame']>, signal: AbortSignal,
  { createImage = () => new Image(), timeoutMs = 1250 }: { createImage?: () => HTMLImageElement; timeoutMs?: number } = {}) {
  const image = createImage();
  try {
    await withPreviewDeadline(async requestSignal => {
      if (requestSignal.aborted) throw new DOMException('Camera preview cancelled.', 'AbortError');
      // Keep the immutable native URL: the SVG reuses the private browser cache.
      image.src = frame.image_url;
      await image.decode();
      if (image.naturalWidth !== frame.width || image.naturalHeight !== frame.height) {
        throw new Error('Live image dimensions do not match its frame geometry.');
      }
    }, signal, timeoutMs);
  } catch (error) {
    // Stop a timed-out preload rather than accumulating hidden image downloads.
    image.removeAttribute('src');
    throw error;
  }
}

export function previewRetryDelay(failures: number): number {
  return Math.min(1000, 125 * 2 ** Math.min(3, Math.max(0, failures - 1)));
}

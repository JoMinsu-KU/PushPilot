import type { LiveCameraSnapshot } from '../../contracts/live-camera';

export const PREVIEW_INTERVAL_MS = 250;
export interface DecodedPreview { url: string; dispose: () => void }

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
  { createImage = () => new Image(), fetcher = fetch, createUrl = URL.createObjectURL,
    revokeUrl = URL.revokeObjectURL, timeoutMs = 1250 }: { createImage?: () => HTMLImageElement;
    fetcher?: typeof fetch; createUrl?: typeof URL.createObjectURL; revokeUrl?: typeof URL.revokeObjectURL;
    timeoutMs?: number } = {}): Promise<DecodedPreview> {
  const image = createImage();
  let url: string | undefined;
  const dispose = () => { image.removeAttribute('src'); if (url) { revokeUrl(url); url = undefined; } };
  try {
    await withPreviewDeadline(async requestSignal => {
      if (requestSignal.aborted) throw new DOMException('Camera preview cancelled.', 'AbortError');
      const response = await fetcher(frame.image_url, { cache: 'no-store', signal: requestSignal });
      if (!response.ok || response.headers.get('content-type')?.split(';')[0] !== 'image/jpeg') {
        throw new Error('Original camera JPEG is unavailable.');
      }
      const blob = await response.blob();
      if (requestSignal.aborted) throw new DOMException('Camera preview cancelled.', 'AbortError');
      if (!blob.size || blob.size > 8 * 1024 * 1024) throw new Error('Camera JPEG size is invalid.');
      // Reuse the exact downloaded bytes for decode AND SVG. No second HTTP
      // cache lookup, canvas, resize, recompression, or inference input change.
      url = createUrl(blob);
      image.src = url;
      await image.decode();
      if (requestSignal.aborted) throw new DOMException('Camera preview cancelled.', 'AbortError');
      if (image.naturalWidth !== frame.width || image.naturalHeight !== frame.height) {
        throw new Error('Live image dimensions do not match its frame geometry.');
      }
    }, signal, timeoutMs);
  } catch (error) {
    dispose();
    throw error;
  }
  return { url: url!, dispose };
}

/** Keep the previous decoded image until React has committed its replacement. */
export function createPreviewResources() {
  const resources = new Map<string, DecodedPreview>();
  return {
    add: (resource: DecodedPreview) => resources.set(resource.url, resource),
    committed: (url: string) => {
      if (!resources.has(url)) return;
      for (const [key, resource] of resources) {
        if (key === url) break;
        resource.dispose(); resources.delete(key);
      }
    },
    dispose: () => { for (const resource of resources.values()) resource.dispose(); resources.clear(); },
  };
}

export function previewRetryDelay(failures: number): number {
  return Math.min(1000, 125 * 2 ** Math.min(3, Math.max(0, failures - 1)));
}

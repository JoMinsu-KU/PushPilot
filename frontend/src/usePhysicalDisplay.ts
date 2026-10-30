import { useEffect, useRef, useState } from 'react';
import type { PhysicalStatus } from '../../contracts/physical';
import { advanceDisplayFeed, displayFeedFresh, displayMatchesStatus, parsePhysicalDisplay, type DisplayFeedState, type PhysicalDisplaySnapshot } from './physicalDisplay';
export { displaySignalLabel } from './physicalDisplay';

/** Optional read-only display telemetry. Its failures never reach the execution hook. */
export function usePhysicalDisplay(status: PhysicalStatus | null, enabled: boolean) {
  const source = useRef(status); source.current = status;
  const [snapshot, setSnapshot] = useState<PhysicalDisplaySnapshot | null>(null);
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    setSnapshot(null); setConnected(false);
    if (!enabled || !source.current?.mission_id) return;
    let disposed = false, timer: number | undefined;
    let feed: DisplayFeedState = { cursor: { producer: null, sequence: -1, retired: [] }, advanced_at: null };
    const controller = new AbortController();
    const heartbeat = window.setInterval(() => {
      if (!displayFeedFresh(feed, performance.now())) {
        setConnected(false);
        setSnapshot(previous => previous && { ...previous, feed_fresh: false });
      }
    }, 500);
    const poll = async () => {
      const request = new AbortController();
      const cancel = () => request.abort();
      controller.signal.addEventListener('abort', cancel, { once: true });
      const deadline = window.setTimeout(cancel, 2500);
      try {
        const response = await fetch('/api/v1/physical/display', { method: 'GET', cache: 'no-store', signal: request.signal });
        if (!response.ok) throw new Error('Display telemetry unavailable');
        const value = parsePhysicalDisplay(await response.json());
        if (disposed) return;
        const now = performance.now();
        feed = advanceDisplayFeed(feed, value, source.current, now);
        const fresh = displayFeedFresh(feed, now);
        setSnapshot({ ...value, feed_fresh: fresh }); setConnected(value.available && fresh);
      } catch {
        if (disposed) return;
        setConnected(false); setSnapshot(previous => previous && { ...previous, feed_fresh: false });
      } finally {
        window.clearTimeout(deadline); controller.signal.removeEventListener('abort', cancel);
      }
      if (!disposed) timer = window.setTimeout(() => void poll(), 1000);
    };
    void poll();
    return () => { disposed = true; controller.abort(); window.clearTimeout(timer); window.clearInterval(heartbeat); };
  }, [enabled, status?.mission_id, status?.plan_id, status?.plan_revision]);
  // Reject a new mission synchronously, before the effect clears the previous poll generation.
  const bound = Boolean(enabled && snapshot && displayMatchesStatus(snapshot, status));
  return { snapshot: bound && snapshot && status ? { ...snapshot, state: status.state } : null, connected: bound && connected };
}

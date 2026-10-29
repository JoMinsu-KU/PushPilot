import { useCallback, useEffect, useRef, useState } from 'react';
import type { PhysicalStatus } from '../../contracts/physical';
import { parsePhysicalStatus } from './physicalMission';

/** Polls state only. Reconnection never starts, retries, or resumes robot motion. */
export function usePhysicalMission() {
  const [status, setStatus] = useState<PhysicalStatus | null>(null);
  const [connected, setConnected] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const pending = useRef(false);
  const current = useRef<PhysicalStatus | null>(null);
  const apply = useCallback((value: unknown) => {
    const next = parsePhysicalStatus(value);
    // A GET started before a mutation must not overwrite its newer result.
    if (current.current && current.current.revision > next.revision) return;
    current.current = next;
    setStatus(next); setConnected(true); setLoaded(true);
  }, []);
  const refresh = useCallback(async () => {
    if (pending.current) return;
    pending.current = true;
    try {
      const response = await fetch('/api/v1/physical/status', { cache: 'no-store', signal: AbortSignal.timeout(5000) });
      if (!response.ok) throw new Error('Robot status unavailable.');
      apply(await response.json());
    } catch { setConnected(false); setLoaded(true); }
    finally { pending.current = false; }
  }, [apply]);
  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 1000);
    return () => window.clearInterval(timer);
  }, [refresh]);
  return { status, connected, loaded, apply, refresh };
}

import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type PointerEvent, type ReactNode } from 'react';
import {
  DEFAULT_CAMERA_VIEWPORT,
  panCameraViewport, pinchCameraViewport, zoomCameraViewport, type CameraViewport,
} from './cameraViewport';

type Position = [number, number];
const midpoint = (first: Position, second: Position): Position => [(first[0] + second[0]) / 2, (first[1] + second[1]) / 2];
const distance = (first: Position, second: Position) => Math.hypot(first[0] - second[0], first[1] - second[1]);

/** Local display navigation only: the original JPEG and AR geometry share one plane. */
export function CameraNavigation({ children, resetToken = 0 }: { children: ReactNode; resetToken?: number }) {
  const host = useRef<HTMLDivElement>(null);
  const pointers = useRef(new Map<number, Position>());
  const current = useRef<CameraViewport>({ ...DEFAULT_CAMERA_VIEWPORT });
  const [view, setView] = useState(current.current);
  const [dragging, setDragging] = useState(false);
  const apply = useCallback((update: (previous: CameraViewport) => CameraViewport) => {
    const next = update(current.current);
    current.current = next;
    setView(next);
  }, []);
  const reset = () => apply(() => ({ ...DEFAULT_CAMERA_VIEWPORT }));
  useEffect(() => {
    apply(() => ({ ...DEFAULT_CAMERA_VIEWPORT }));
  }, [resetToken, apply]);
  const position = useCallback((x: number, y: number): Position | null => {
    const rect = host.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) return null;
    return [(x - rect.left) / rect.width - .5, (y - rect.top) / rect.height - .5];
  }, []);

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const wheel = (event: WheelEvent) => {
      const anchor = position(event.clientX, event.clientY);
      if (!anchor || !Number.isFinite(event.deltaY)) return;
      event.preventDefault();
      const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? element.clientHeight : 1;
      const delta = Math.max(-240, Math.min(240, event.deltaY * unit));
      apply(previous => zoomCameraViewport(previous, previous.zoom * Math.exp(-delta * .002), anchor));
    };
    element.addEventListener('wheel', wheel, { passive: false });
    return () => element.removeEventListener('wheel', wheel);
  }, [apply, position]);

  const pointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || pointers.current.size >= 2) return;
    const point = position(event.clientX, event.clientY);
    if (!point) return;
    event.preventDefault();
    pointers.current.set(event.pointerId, point);
    event.currentTarget.setPointerCapture(event.pointerId);
    event.currentTarget.focus({ preventScroll: true });
    setDragging(true);
  };
  const pointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!pointers.current.has(event.pointerId)) return;
    const point = position(event.clientX, event.clientY);
    if (!point) return;
    event.preventDefault();
    const previous = [...pointers.current.values()];
    const last = pointers.current.get(event.pointerId)!;
    pointers.current.set(event.pointerId, point);
    const next = [...pointers.current.values()];
    if (previous.length === 2 && next.length === 2) {
      // Distances use physical pixels so the pinch ratio is independent of aspect ratio.
      const rect = event.currentTarget.getBoundingClientRect();
      const pixels = (value: Position): Position => [value[0] * rect.width, value[1] * rect.height];
      const beforeDistance = distance(pixels(previous[0]), pixels(previous[1]));
      const ratio = beforeDistance > 1 ? distance(pixels(next[0]), pixels(next[1])) / beforeDistance : 1;
      apply(value => pinchCameraViewport(value, midpoint(previous[0], previous[1]), midpoint(next[0], next[1]), ratio));
    } else {
      apply(value => panCameraViewport(value, point[0] - last[0], point[1] - last[1]));
    }
  };
  const pointerEnd = (event: PointerEvent<HTMLDivElement>) => {
    pointers.current.delete(event.pointerId);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    setDragging(pointers.current.size > 0);
  };
  const cancel = () => { pointers.current.clear(); setDragging(false); };
  const keyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.target !== event.currentTarget) return;
    if (event.key === '+' || event.key === '=') apply(value => zoomCameraViewport(value, value.zoom * 1.2));
    else if (event.key === '-' || event.key === '_') apply(value => zoomCameraViewport(value, value.zoom / 1.2));
    else if (['0', 'Home', 'Escape'].includes(event.key)) reset();
    else if (event.key === 'ArrowLeft') apply(value => panCameraViewport(value, -.05, 0));
    else if (event.key === 'ArrowRight') apply(value => panCameraViewport(value, .05, 0));
    else if (event.key === 'ArrowUp') apply(value => panCameraViewport(value, 0, -.05));
    else if (event.key === 'ArrowDown') apply(value => panCameraViewport(value, 0, .05));
    else return;
    event.preventDefault();
  };

  return <div ref={host} className={`camera-viewport${dragging ? ' is-dragging' : ''}`} tabIndex={0}
      role="region" aria-label="Camera viewport" aria-description="Drag to move. Pinch to zoom. Arrow keys move the view; zero or Fit camera view resets it."
      onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerEnd}
      onPointerCancel={cancel} onLostPointerCapture={pointerEnd} onBlur={cancel} onKeyDown={keyDown}>
      <div className="camera-image-plane" style={{ transform: `translate(${view.panX * 100}%, ${view.panY * 100}%) scale(${view.zoom})` }}>
        {children}
      </div>
    </div>;
}

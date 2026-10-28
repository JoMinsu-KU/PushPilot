import type { CSSProperties } from 'react';

export type IconName = 'arrow' | 'chevron' | 'eye' | 'mic' | 'text' | 'home' | 'clock' | 'settings' | 'camera' | 'check' | 'pause' | 'play' | 'refresh' | 'stop' | 'glasses' | 'car' | 'shield' | 'close' | 'spark' | 'route' | 'upload' | 'plus' | 'minus';
const paths: Record<IconName, React.ReactNode> = {
  arrow: <><path d="M4 12h15M13 5l7 7-7 7" /></>,
  chevron: <path d="m9 5 7 7-7 7" />,
  eye: <><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></>,
  mic: <><rect x="9" y="2" width="6" height="13" rx="3" /><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8" /></>,
  text: <path d="M4 5h16M4 12h16M4 19h10" />,
  home: <><path d="m3 10 9-8 9 8v11h-6v-7H9v7H3Z" /></>,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 6v6l4 2" /></>,
  settings: <><path d="m9 3 1-1h4l1 3 3 1 3 3-1 3 1 3-3 3-3 1-1 3h-4l-1-3-3-1-3-3 1-3-1-3 3-3Z" /><circle cx="12" cy="12" r="3" /></>,
  camera: <><path d="M3 6h5l2-3h4l2 3h5v15H3Z" /><circle cx="12" cy="13" r="4" /></>,
  check: <path d="m5 12 4 4L20 5" />,
  pause: <><path d="M8 5v14M16 5v14" /></>,
  play: <path d="m8 4 12 8-12 8Z" />,
  refresh: <><path d="M20 10a8 8 0 1 0-1 7M20 4v6h-6" /></>,
  stop: <rect x="5" y="5" width="14" height="14" rx="2" />,
  glasses: <><path d="M2 9h8l1 2h2l1-2h8l-1 8h-7l-1-5h-2l-1 5H3Z" /></>,
  car: <><path d="m5 8 2-4h10l2 4 2 3v8H3v-8ZM6 12h2m8 0h2M5 19v2m14-2v2M5 8h14" /></>,
  shield: <><path d="m12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6Z" /><path d="m8 11 3 3 5-6" /></>,
  close: <path d="m6 6 12 12M18 6 6 18" />,
  spark: <><path d="m12 2 2.5 7.5L22 12l-7.5 2.5L12 22l-2.5-7.5L2 12l7.5-2.5Z" /></>,
  route: <><circle cx="5" cy="19" r="2" /><circle cx="19" cy="5" r="2" /><path d="M7 19h8a4 4 0 0 0 0-8H9a4 4 0 0 1 0-8h8" /></>,
  upload: <><path d="M4 16v5h16v-5M12 16V3m-5 5 5-5 5 5" /></>,
  plus: <path d="M5 12h14M12 5v14" />,
  minus: <path d="M5 12h14" />,
};
export function Icon({ name, size = 22, style, className = '' }: { name: IconName; size?: number; style?: CSSProperties; className?: string }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={style} className={className}>{paths[name]}</svg>;
}
export function BrandMark() {
  return <svg width="39" height="39" viewBox="0 0 40 40" aria-hidden="true"><path fill="currentColor" d="M2 18 23 5v15L2 33Z"/><path fill="currentColor" d="m17 25 21-13v23Z"/><path fill="currentColor" opacity=".55" d="m17 25 6-5v8Z"/></svg>;
}

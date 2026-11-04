// Design review only; no mission state or equipment connection.
// Standalone Spatial design preview: camera views and signal appearance controls.
import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { CityModelView } from './CityModelView';
import type { CitySignalState } from './citySignal';
import './fonts.css';
import './spatial-preview.css';

/** Interactive preview shell around the city model viewer. */
function SpatialSignalPreview() {
  const [signal, setSignal] = useState<CitySignalState>('base');
  const [camera, setCamera] = useState<'wide' | 'signal'>('wide');
  const [cameraRevision, setCameraRevision] = useState(0);
  const selectCamera = (view: 'wide' | 'signal') => { setCamera(view); setCameraRevision(current => current + 1); };
  const green = signal === 'green-approved';
  const red = signal === 'red-observed';
  return <main className="spatial-preview">
    <CityModelView map={null} display={null} signalState={signal} previewCamera={camera} previewCameraRevision={cameraRevision}/>
    <header className="preview-header preview-glass">
      <a href="/spatial-preview.html" className="preview-brand" aria-label="PushPilot Spatial preview">
        <img src="/favicon.svg" alt=""/><strong>PushPilot</strong><span>/</span><span>Spatial</span>
      </a>
      <span className="preview-badge"><i/>Design preview</span>
    </header>
    <nav className="preview-cameras preview-glass" aria-label="Camera views">
      <button className={camera === 'wide' ? 'selected' : ''} aria-pressed={camera === 'wide'} onClick={() => selectCamera('wide')}>City overview</button>
      <button className={camera === 'signal' ? 'selected' : ''} aria-pressed={camera === 'signal'} onClick={() => selectCamera('signal')}>Signal detail</button>
    </nav>
    <section className="preview-signal-controls preview-glass" aria-label="Traffic signal preview controls">
      <div className="preview-section-title"><span><i className={green ? 'green' : red ? 'red' : ''}/>Traffic signal</span><small>Preview controls</small></div>
      <div className="preview-state" aria-live="polite">
        <strong>{green ? 'Green approved' : red ? 'Red observed' : 'Both colors visible'}</strong>
        <p>{green ? 'Only the lower green face illuminates.' : red ? 'Only the upper red face illuminates.' : 'Green and red retain their printed colors.'}</p>
      </div>
      <div className="preview-state-options" role="group" aria-label="Signal appearance">
        <button className={signal === 'base' ? 'selected' : ''} aria-pressed={signal === 'base'} onClick={() => setSignal('base')}><span className="mini-signal"><i/><i/></span>Base state</button>
        <button className={red ? 'selected' : ''} aria-pressed={red} onClick={() => setSignal('red-observed')}><span className="red-lamp"/>Red observed</button>
        <button className={green ? 'selected' : ''} aria-pressed={green} onClick={() => setSignal('green-approved')}><span className="green-lamp"/>Green approved</button>
      </div>
    </section>
    <div className="preview-hint preview-glass">Drag to orbit<span>·</span>Pinch or scroll to zoom</div>
  </main>;
}

createRoot(document.getElementById('root')!).render(<SpatialSignalPreview/>);

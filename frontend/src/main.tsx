// Mounts App once; no services start from this entry point.
// React entry point: mount the operator workspace and load global styles.
import React from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import './fonts.css';
import './styles.css';
import './goal-intent.css';
import './tablet.css';
import './typography.css';
import './voice-input.css';

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);

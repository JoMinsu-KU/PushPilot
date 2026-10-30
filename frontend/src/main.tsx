import React from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import './fonts.css';
import './styles.css';
import './goal-intent.css';
import './tablet.css';
import './typography.css';

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);

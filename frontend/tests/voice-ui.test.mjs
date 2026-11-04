import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

// Compile the actual presentation components without a listener, microphone or provider.
const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)), configFile: false,
  server: { middlewareMode: true, watch: null }, appType: 'custom' });
test.after(() => server.close());
const { GoalIntentBar, VoiceInputOptions } = await server.ssrLoadModule('/src/GoalIntent.tsx');

const state = (update = {}) => ({ phase: 'idle', levels: Array(40).fill(0), elapsed: 0,
  text: '', transcript: null, error: '', ...update });
const calls = [];
const callback = (name) => () => calls.push(name);
const renderBar = (voice, canRecord = true) => renderToStaticMarkup(React.createElement(GoalIntentBar, {
  query: 'The accepted typed goal', source: 'typed', voice, canRecord,
  onQuery: callback('query'), onVoice: callback('record'), onCancelVoice: callback('cancel'),
}));
const renderOptions = (voice, extra = {}) => renderToStaticMarkup(React.createElement(VoiceInputOptions, {
  voice, canEdit: true, onContinue: callback('type'), onRecord: callback('record'),
  onStop: callback('finish'), onCancel: callback('cancel'), onText: callback('edit'),
  onUseGoal: callback('create'), ...extra,
}));
const buttons = (html) => html.match(/<button\b[^>]*>[\s\S]*?<\/button>/g) ?? [];
const button = (html, label) => {
  const found = buttons(html).find((markup) => markup.includes(label));
  assert.ok(found, `Missing button: ${label}`);
  return found;
};

test('idle voice keeps the accepted query and requires an explicit recording action', () => {
  const html = renderBar(state());
  assert.match(html, /The accepted typed goal/);
  assert.doesNotMatch(button(html, 'Record a voice goal'), /disabled=""/);
  assert.match(button(renderBar(state(), false), 'Record a voice goal'), /disabled=""/);
  assert.doesNotMatch(renderOptions(state()), /voice-transcript|Create a plan|Approved/);
  assert.deepEqual(calls, [], 'rendering cannot start capture, submit a goal or approve a mission');
});

test('recording shows supplied microphone levels, elapsed time and explicit finish or cancel controls', () => {
  const voice = state({ phase: 'recording', elapsed: 7.8,
    levels: Array.from({ length: 40 }, (_, index) => index === 39 ? 0.25 : 0) });
  const bar = renderBar(voice, false);
  assert.match(bar, /aria-label="Live microphone volume"/);
  assert.equal((bar.match(/<i style="height:/g) ?? []).length, 40);
  assert.match(bar, /height:6px/);
  assert.match(bar, /height:48px/);
  assert.match(bar, /<output>7s \/ 20s<\/output>/);
  assert.doesNotMatch(button(bar, 'Finish recording and recognize speech'), /disabled=""/,
    'finishing remains available when a recording is already active');
  assert.ok(button(bar, 'Cancel voice input'));
  const modal = renderOptions(voice);
  assert.ok(button(modal, 'Finish recording'));
  assert.ok(button(modal, 'Cancel'));
  assert.doesNotMatch(modal, /<textarea|Create a plan|Approved/);
  assert.deepEqual(calls, []);
});

test('permission and transcription waits expose cancellation without accepting an unfinished transcript', () => {
  for (const phase of ['requesting', 'transcribing']) {
    const voice = state({ phase });
    const bar = renderBar(voice);
    assert.match(bar, /role="status"/);
    assert.match(bar, /voice-spinner/);
    assert.match(button(bar, 'Record a voice goal'), /disabled=""/);
    assert.ok(button(bar, 'Cancel voice input'));
    assert.doesNotMatch(bar, /The accepted typed goal/);
    const modal = renderOptions(voice);
    assert.match(button(modal, 'Recognizing'), /disabled=""/);
    assert.ok(button(modal, 'Cancel'));
    assert.doesNotMatch(modal, /<textarea|Create a plan|Approved/);
  }
  assert.deepEqual(calls, []);
});

test('recognized words are an escaped editable candidate with a separate Create a plan action', () => {
  const voice = state({ phase: 'ready', text: '피자집에서 빌라로 가 줘 <script>alert(1)</script>' });
  const original = structuredClone(voice);
  Object.freeze(voice.levels); Object.freeze(voice);
  const bar = renderBar(voice);
  assert.match(bar, /Review the recognized goal before creating a plan/);
  assert.match(bar, /피자집에서 빌라로 가 줘/);
  const modal = renderOptions(voice);
  assert.match(modal, /Review transcript/);
  assert.match(modal, /<textarea[^>]*id="voice-transcript"/);
  assert.match(modal, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.doesNotMatch(modal, /<script>/);
  assert.match(modal, /Creating a plan does not approve it or start the robot/);
  assert.doesNotMatch(button(modal, 'Create a plan'), /disabled=""/);
  assert.ok(button(modal, 'Discard')); assert.ok(button(modal, 'Record again'));
  assert.ok(button(modal, 'Type instead'));
  assert.ok(buttons(modal).every((markup) => !/Approve plan|Start robot|Resume/.test(markup)));
  assert.deepEqual(voice, original);
  assert.deepEqual(calls, [], 'a ready render still requires an operator click');
});

test('empty, overlong, locked and busy candidates cannot create plans or restart capture', () => {
  for (const text of ['', '   ', 'x'.repeat(501)]) {
    const html = renderOptions(state({ phase: 'ready', text }));
    assert.match(button(html, 'Create a plan'), /disabled=""/);
  }
  const ready = state({ phase: 'ready', text: 'Go to Villa.' });
  const locked = renderOptions(ready, { canEdit: false });
  assert.match(locked, /<textarea[^>]*disabled=""/);
  assert.match(button(locked, 'Create a plan'), /disabled=""/);
  assert.match(button(locked, 'Record again'), /disabled=""/);
  assert.ok(button(locked, 'View original query'));
  const busy = renderOptions(ready, { busy: true });
  assert.match(button(busy, 'Creating a plan'), /disabled=""/);
  assert.match(button(busy, 'Record again'), /disabled=""/);
  assert.deepEqual(calls, []);
});

test('capture failures show the original error and keep typed fallback without invented words', () => {
  const html = renderOptions(state({ phase: 'error', error: 'Microphone permission was denied.' }));
  assert.match(html, /role="alert"/);
  assert.match(html, /Microphone permission was denied/);
  assert.ok(button(html, 'Type instead'));
  assert.doesNotMatch(button(html, 'Record a voice goal'), /disabled=""/);
  assert.doesNotMatch(html, /<textarea|Create a plan|Approved/);
  assert.deepEqual(calls, []);
});

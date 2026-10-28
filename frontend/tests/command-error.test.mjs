import assert from 'node:assert/strict';
import test from 'node:test';
import { commandErrorMessage } from '../src/commandError.ts';

test('blocked live registration presents its original actionable code and message', () => {
  const message = 'A fixed drawing reference without contradictory view evidence is required; no automatic refit was performed.';
  assert.equal(commandErrorMessage({ detail: { code: 'LIVE_CAPTURE_REGISTRATION', message } }, 409),
    `LIVE_CAPTURE_REGISTRATION: ${message}`);
  assert.equal(commandErrorMessage({ detail: { code: 'LIVE_CAPTURE_CHANGED', message: 'The camera or registered map changed while MUSE was working.' } }, 409),
    'LIVE_CAPTURE_CHANGED: The camera or registered map changed while MUSE was working.');
});

test('actual workspace revision conflicts retain the existing operator instruction', () => {
  assert.equal(commandErrorMessage({ detail: 'Workspace changed. Refresh state before submitting this command.' }, 409),
    'The mission state changed. Review the current state before trying again.');
});

test('other bounded API errors remain readable without assuming their shape', () => {
  assert.equal(commandErrorMessage({ detail: { code: 'MUSE_NOT_CONFIGURED', message: 'MUSE is not configured on the backend.' } }, 503),
    'MUSE_NOT_CONFIGURED: MUSE is not configured on the backend.');
  assert.equal(commandErrorMessage({ detail: 'MUSE planning failed.' }, 502), 'MUSE planning failed.');
  assert.equal(commandErrorMessage({ detail: { message: 'Review input is incomplete.' } }, 422), 'Review input is incomplete.');
  assert.equal(commandErrorMessage(null, 502), 'The request could not be completed. Refresh the state and try again.');
  assert.equal(commandErrorMessage({ detail: [{ loc: ['body', 'text'] }] }, 422),
    'The request could not be completed. Refresh the state and try again.');
});

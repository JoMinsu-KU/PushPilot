import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequestId } from '../src/requestId.ts';

const uuidV4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

test('LAN HTTP fallback creates a valid UUID when randomUUID is unavailable', () => {
  let called = false;
  const result = createRequestId({
    getRandomValues(bytes) {
      called = true;
      bytes.fill(255);
      return bytes;
    },
  });
  assert.equal(called, true);
  assert.match(result, uuidV4);
  assert.equal(result, 'ffffffff-ffff-4fff-bfff-ffffffffffff');
});

test('the least capable browser fallback still matches the API UUID contract', () => {
  assert.match(createRequestId({}), uuidV4);
});

test('native UUID generation preserves the source method context', () => {
  const source = {
    marker: 'source',
    randomUUID() {
      assert.equal(this.marker, 'source');
      return '12345678-1234-4234-8234-123456789abc';
    },
  };
  assert.equal(createRequestId(source), '12345678-1234-4234-8234-123456789abc');
});

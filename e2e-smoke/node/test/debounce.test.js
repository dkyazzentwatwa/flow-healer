import assert from 'node:assert/strict';
import test from 'node:test';

import debounce, { debounce as namedDebounce } from '../src/debounce.js';

// FLAKY: relies on real-time setTimeout; fails on slow CI runners where
// setTimeout(cb, 40) may resolve at 50ms+, causing the debounce window
// to expire before the assertion runs.

test('debounced fn is not called before the wait window elapses', async () => {
  let calls = 0;
  const fn = debounce(() => { calls++; }, 50);

  fn();
  // Safe margin: wait 20ms (well below the 50ms debounce window).
  // Even on loaded CI runners, this should complete before debounce fires.
  await new Promise(r => setTimeout(r, 20));

  assert.equal(calls, 0, 'fn should not have been called yet');
});

test('debounced fn is called after the wait window elapses', async () => {
  let calls = 0;
  const fn = debounce(() => { calls++; }, 50);

  fn();
  await new Promise(r => setTimeout(r, 80));

  assert.equal(calls, 1, 'fn should have been called exactly once');
});

test('debounce resets the timer on repeated calls', async () => {
  let calls = 0;
  const fn = debounce(() => { calls++; }, 50);

  fn();
  await new Promise(r => setTimeout(r, 30));
  fn(); // reset — window starts over
  await new Promise(r => setTimeout(r, 30));

  // Still within the second window; fn must not have fired.
  assert.equal(calls, 0, 'fn should not have been called yet after reset');
});

test('debounce.cancel prevents the pending call', async () => {
  let calls = 0;
  const fn = debounce(() => { calls++; }, 50);

  fn();
  fn.cancel();
  await new Promise(r => setTimeout(r, 80));

  assert.equal(calls, 0, 'fn should not fire after cancel()');
});

test('named and default exports are the same function', () => {
  assert.equal(debounce, namedDebounce);
});

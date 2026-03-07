import assert from 'node:assert/strict';
import test from 'node:test';

import { add } from './add.mjs';

test('add returns the sum of two numbers', () => {
  assert.equal(add(2, 3), 5);
});

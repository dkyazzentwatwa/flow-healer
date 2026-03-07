import assert from 'node:assert/strict';
import test from 'node:test';

import { add } from '../src/add.js';

test('add returns the sum of two numbers', () => {
  assert.equal(add(2, 3), 5);
});

test('add handles zero correctly', () => {
  assert.equal(add(0, 0), 0);
});

test('add handles negative numbers', () => {
  assert.equal(add(-2, 3), 1);
});

test('add handles larger integers', () => {
  assert.equal(add(123456789, 987654321), 1111111110);
});

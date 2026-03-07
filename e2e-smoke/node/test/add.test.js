import assert from 'node:assert/strict';
import test from 'node:test';

import { add } from '../src/add.js';

test('add returns the sum of two numbers', () => {
  assert.equal(add(2, 3), 5);
});

test('add handles zero when both inputs are zero', () => {
  assert.equal(add(0, 0), 0);
  assert.equal(add(0, 7), 7);
  assert.equal(add(7, 0), 7);
});

test('add normalizes negative zero results', () => {
  assert.equal(add(-0, -0), 0);
});

test('add handles zero as the first input', () => {
  assert.equal(add(0, 7), 7);
});

test('add handles zero as the second input', () => {
  assert.equal(add(7, 0), 7);
});

test('add handles negative numbers', () => {
  assert.equal(add(-2, 3), 1);
});

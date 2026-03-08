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
  assert.equal(add(3, -2), 1);
  assert.equal(add(-2, -3), -5);
});

test('add handles two negative numbers', () => {
  assert.equal(add(-2, -3), -5);
});

test('add handles larger integers', () => {
  assert.equal(add(123456789, 987654321), 1111111110);
});

test('add handles large bigint inputs', () => {
  assert.equal(
    add(9_007_199_254_740_991n, 2n),
    9_007_199_254_740_993n,
  );
});

test('add handles negative bigint combinations', () => {
  assert.equal(add(-9_007_199_254_740_991n, 1n), -9_007_199_254_740_990n);
  assert.equal(add(-4n, 4n), 0n);
});

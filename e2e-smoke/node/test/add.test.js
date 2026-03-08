import assert from 'node:assert/strict';
import test from 'node:test';

import { add } from '../src/add.js';

const addTestCases = [
  { name: 'returns 5 for two positive numbers', left: 2, right: 3, expected: 5 },
  { name: 'returns 0 when both inputs are zero', left: 0, right: 0, expected: 0 },
  {
    name: 'returns the right value when the left input is zero',
    left: 0,
    right: 7,
    expected: 7,
  },
  {
    name: 'returns the left value when the right input is zero',
    left: 7,
    right: 0,
    expected: 7,
  },
  { name: 'normalizes negative zero to 0', left: -0, right: -0, expected: 0 },
  {
    name: 'adds a negative number to a positive number',
    left: -2,
    right: 3,
    expected: 1,
  },
  {
    name: 'adds a positive number to a negative number',
    left: 3,
    right: -2,
    expected: 1,
  },
  { name: 'adds two negative numbers', left: -2, right: -3, expected: -5 },
  {
    name: 'adds larger integers',
    left: 123456789,
    right: 987654321,
    expected: 1111111110,
  },
  {
    name: 'adds large bigint values without losing precision',
    left: 9007199254740993n,
    right: 7n,
    expected: 9007199254741000n,
  },
  {
    name: 'adds mixed integer number and bigint inputs',
    left: 7,
    right: 9007199254740993n,
    expected: 9007199254741000n,
  },
  {
    name: 'normalizes zero bigint sums to 0n',
    left: -5n,
    right: 5n,
    expected: 0n,
  },
  {
    name: 'promotes safe integer inputs to bigint when the sum exceeds safe precision',
    left: Number.MAX_SAFE_INTEGER,
    right: 2,
    expected: 9007199254740993n,
  },
  {
    name: 'promotes large negative integer inputs to bigint when the sum exceeds safe precision',
    left: Number.MIN_SAFE_INTEGER,
    right: -2,
    expected: -9007199254740993n,
  },
  {
    name: 'promotes two large safe integers when their combined sum exceeds safe precision',
    left: Number.MAX_SAFE_INTEGER,
    right: Number.MAX_SAFE_INTEGER,
    expected: 18014398509481982n,
  },
];

function assertScenarioResult({ left, right, expected }) {
  assert.equal(add(left, right), expected);
}

test('add returns the expected sum for each scenario', async (t) => {
  for (const { name, ...testCase } of addTestCases) {
    await t.test(name, () => assertScenarioResult(testCase));
  }
});

test('add preserves regular number semantics for non-integer inputs', () => {
  assert.ok(Number.isNaN(add(Number.NaN, 1)));
  assert.equal(add(0.1, 0.2), 0.30000000000000004);
});

test('add folds larger input combinations through the same promotion rules', () => {
  assert.equal(add(1, 2, 3, 4), 10);
  assert.equal(add(1n, 2, 3n, 4), 10n);
  assert.equal(add(1, 2, 3, 4, 5), 15);
  assert.equal(add(1n, 2, 3, 4, 5n), 15n);
  assert.equal(add(0, 1n, 2, 3), 6n);
  assert.equal(add(Number.MAX_SAFE_INTEGER, 1, 1), 9007199254740993n);
  assert.equal(add(Number.MAX_SAFE_INTEGER - 1, 1, 1), 9007199254740992n);
  assert.equal(add(2, -2, 0), 0);
  assert.equal(add(2n, -2, 0), 0n);
  assert.equal(add(0, Number.MAX_SAFE_INTEGER, 1), 9007199254740992n);
  assert.equal(add(-0, 0, 0), 0);
});

test('add keeps unsafe integer number inputs on normal number semantics', () => {
  const oversizedNumber = Number.MAX_SAFE_INTEGER + 2;

  assert.equal(add(oversizedNumber, 1), oversizedNumber + 1);
});

test('add keeps existing single-value and empty-call behavior', () => {
  assert.equal(add(), 0);
  assert.equal(add(-0), 0);
  assert.equal(add(5n), 5n);
  assert.equal(add(Number.MAX_SAFE_INTEGER), Number.MAX_SAFE_INTEGER);
  assert.equal(add(0n), 0n);
});

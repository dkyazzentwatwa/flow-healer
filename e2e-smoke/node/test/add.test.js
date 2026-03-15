import assert from 'node:assert/strict';
import test from 'node:test';
import vm from 'node:vm';

import addDefault, { add, addMany } from '../src/add.js';

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
    name: 'promotes negative safe integers that cross the lower boundary',
    left: Number.MIN_SAFE_INTEGER,
    right: -1,
    expected: -9007199254740992n,
  },
  {
    name: 'promotes two large safe integers when their combined sum exceeds safe precision',
    left: Number.MAX_SAFE_INTEGER,
    right: Number.MAX_SAFE_INTEGER,
    expected: 18014398509481982n,
  },
];

function assertAddResult({ left, right, expected }) {
  const actual = add(left, right);
  assert.equal(actual, expected);
}

function repeatValue(length, value) {
  return Array.from({ length }, () => value);
}

function assertSumForInputs(inputs, expected) {
  assert.equal(add(...inputs), expected);
}

const longerInputListCases = [
  { name: 'adds four numbers', inputs: [1, 2, 3, 4], expected: 10 },
  { name: 'keeps bigint promotion for mixed inputs', inputs: [1n, 2, 3n, 4], expected: 10n },
  { name: 'adds five number inputs', inputs: [1, 2, 3, 4, 5], expected: 15 },
  { name: 'keeps bigint output when bigint values are present', inputs: [1n, 2, 3, 4, 5n], expected: 15n },
  { name: 'promotes zero-prefixed mixed inputs to bigint', inputs: [0, 1n, 2, 3], expected: 6n },
  { name: 'promotes zero-prefixed overflowing number inputs', inputs: [0, Number.MAX_SAFE_INTEGER, 2], expected: 9007199254740993n },
  { name: 'promotes sums beyond max safe integer', inputs: [Number.MAX_SAFE_INTEGER, 1, 1], expected: 9007199254740993n },
  { name: 'promotes boundary sums that reach unsafe precision', inputs: [Number.MAX_SAFE_INTEGER - 1, 1, 1], expected: 9007199254740992n },
  { name: 'keeps balanced number inputs at zero', inputs: [2, -2, 0], expected: 0 },
  { name: 'keeps balanced mixed inputs at zero bigint', inputs: [2n, -2, 0], expected: 0n },
  { name: 'promotes trailing overflow past max safe integer', inputs: [0, Number.MAX_SAFE_INTEGER, 1], expected: 9007199254740992n },
  { name: 'normalizes negative zero inside longer number lists', inputs: [-0, 0, 0], expected: 0 },
];

test('add returns the expected sum for each named scenario', async (t) => {
  for (const testCase of addTestCases) {
    const { name } = testCase;
    await t.test(name, () => assertAddResult(testCase));
  }
});

test('add keeps default and named exports aligned', () => {
  assert.equal(addDefault, add);
  assert.equal(addDefault(2, 3), 5);
});

test('addMany adds three numeric operands', () => {
  assert.equal(addMany(1, 2, 3), 6);
});

test('addMany normalizes numeric string operands like add input normalization', () => {
  assert.equal(addMany('1', '2', '3'), 6);
});

test('addMany handles an empty operand list', () => {
  assert.equal(addMany(), 0);
});

test('addMany adds two finite operands', () => {
  assert.equal(addMany(5, 7), 12);
});

test('addMany preserves the identity of a single operand', () => {
  assert.equal(addMany(5), 5);
});

test('addMany rejects one invalid operand', () => {
  assert.throws(() => addMany(1, Number.POSITIVE_INFINITY, 3), {
    name: 'TypeError',
  });
});

test('addMany sums more than three finite operands', () => {
  assert.equal(addMany(1, 2, 3, 4, 5), 15);
});

test('addMany normalizes numeric string operands across variadic inputs', () => {
  assert.equal(addMany('1', ' 2 ', '3', '4'), 10);
});

test('addMany unwraps value-wrapped operands across variadic inputs', () => {
  assert.equal(
    addMany(
      { value: '1' },
      { value: { value: '2' } },
      { value: 3 },
      { value: { value: ' 4 ' } },
    ),
    10,
  );
});

test('addMany rejects an invalid operand among a longer list', () => {
  assert.throws(() => addMany(1, 2, Number.POSITIVE_INFINITY, 4), {
    name: 'TypeError',
  });
});

test('addMany promotes overflow sums to bigint when needed', () => {
  assert.equal(
    addMany(0, Number.MAX_SAFE_INTEGER, 2),
    9007199254740993n,
  );
});

test('addMany rejects unsafe integers after a variadic overflow boundary', () => {
  assert.throws(
    () => addMany(Number.MAX_SAFE_INTEGER, 1, Number.MAX_SAFE_INTEGER + 1),
    {
      name: 'RangeError',
      message:
        'Cannot mix a variadic bigint-overflow sum with unsafe integer numbers; convert the number input to bigint first.',
    },
  );
});

test('add preserves regular number semantics for non-integer inputs', () => {
  const nanResult = add(Number.NaN, 1);
  const decimalResult = add(0.1, 0.2);

  assert.ok(Number.isNaN(nanResult));
  assert.equal(decimalResult, 0.30000000000000004);
});

test('add preserves NaN semantics across mixed-number and bigint tails', () => {
  const mixedTailResult = add(1, Number.NaN, 2n);
  const leadingNaNResult = add(Number.NaN, 1n);
  const trailingNaNResult = add(1n, Number.NaN);

  assert.ok(Number.isNaN(mixedTailResult));
  assert.ok(Number.isNaN(leadingNaNResult));
  assert.ok(Number.isNaN(trailingNaNResult));
});

test('add rejects string operands for two-argument calls', () => {
  assert.throws(() => add('2', 3), {
    name: 'TypeError',
    message: 'add() does not accept string operands.',
  });
  assert.throws(() => add(2, '3'), {
    name: 'TypeError',
    message: 'add() does not accept string operands.',
  });
});

test('add rejects string operands for variadic calls', () => {
  assert.throws(() => add(1, '2', 3), {
    name: 'TypeError',
    message: 'add() does not accept string operands.',
  });
  assert.throws(() => add(...[1, 2, '3']), {
    name: 'TypeError',
    message: 'add() does not accept string operands.',
  });
});

test('add rejects cross-realm boxed string operands for two-argument calls', () => {
  const boxedString = vm.runInNewContext('Object("2")');

  assert.throws(() => add(boxedString, 3), {
    name: 'TypeError',
    message: 'add() does not accept string operands.',
  });
  assert.throws(() => add(2, boxedString), {
    name: 'TypeError',
    message: 'add() does not accept string operands.',
  });
});

test('add rejects cross-realm boxed string operands for variadic calls', () => {
  const boxedString = vm.runInNewContext('Object("2")');

  assert.throws(() => add(1, boxedString, 3), {
    name: 'TypeError',
    message: 'add() does not accept string operands.',
  });
  assert.throws(() => add(...[1, 2, boxedString]), {
    name: 'TypeError',
    message: 'add() does not accept string operands.',
  });
});

test('add keeps ordinary objects with numeric valueOf on the addition path', () => {
  const numericObject = {
    valueOf() {
      return 2;
    },
  };

  assert.equal(add(numericObject, 3), 5);
  assert.equal(add(1, numericObject, 3), 6);
});

test('add keeps a leading undefined input on normal NaN semantics in longer lists', () => {
  assert.ok(Number.isNaN(add(undefined, 1, 2)));
});

test('add rejects string operands in two-argument calls', () => {
  assert.throws(() => add('2', 3), {
    name: 'TypeError',
    message: 'add() does not accept string operands.',
  });
  assert.throws(() => add(2, '3'), {
    name: 'TypeError',
    message: 'add() does not accept string operands.',
  });
  assert.throws(() => add.call(null, '2', 3), {
    name: 'TypeError',
    message: 'add() does not accept string operands.',
  });
});

test('add rejects string operands in variadic calls', () => {
  assert.throws(() => add('1', 2, 3), {
    name: 'TypeError',
    message: 'add() does not accept string operands.',
  });
  assert.throws(() => add(1, '2', 3), {
    name: 'TypeError',
    message: 'add() does not accept string operands.',
  });
  assert.throws(() => add(1n, 2, '3'), {
    name: 'TypeError',
    message: 'add() does not accept string operands.',
  });
  assert.throws(() => add.apply(null, [1, '2', 3]), {
    name: 'TypeError',
    message: 'add() does not accept string operands.',
  });
});

test('add applies the same promotion rules to longer input lists', async (t) => {
  for (const testCase of longerInputListCases) {
    await t.test(testCase.name, () =>
      assertSumForInputs(testCase.inputs, testCase.expected),
    );
  }
});

test('add handles long input lists without changing promotion behavior', () => {
  const manyOnes = repeatValue(5000, 1);
  const manyNegativeOnes = repeatValue(5000, -1);
  const balancedNumberInputs = [
    ...repeatValue(3000, 2),
    ...repeatValue(3000, -2),
  ];
  const precisionBoundaryInputs = [
    Number.MAX_SAFE_INTEGER - 3,
    ...repeatValue(6, 1),
  ];
  const balancedBigIntInputs = [
    ...repeatValue(2000, 1n),
    ...repeatValue(2000, -1n),
  ];
  const alternatingMixedInputs = Array.from({ length: 4000 }, (_, index) =>
    index % 2 === 0 ? 1n : 1,
  );

  assertSumForInputs(manyOnes, 5000);
  assertSumForInputs(manyNegativeOnes, -5000);
  assertSumForInputs(balancedNumberInputs, 0);
  assertSumForInputs(precisionBoundaryInputs, 9007199254740994n);
  assertSumForInputs(balancedBigIntInputs, 0n);
  assertSumForInputs(alternatingMixedInputs, 4000n);
});

test('add keeps unsafe integer number inputs on normal number semantics', () => {
  const oversizedNumber = Number.MAX_SAFE_INTEGER + 2;

  assert.equal(add(oversizedNumber, 1), oversizedNumber + 1);
});

test('add rejects bigint mixed with integer numbers beyond safe precision', () => {
  const oversizedNumber = Number.MAX_SAFE_INTEGER + 2;
  const oversizedNegativeNumber = Number.MIN_SAFE_INTEGER - 2;

  assert.throws(() => add(oversizedNumber, 1n), {
    name: 'RangeError',
    message: 'Cannot mix bigint values with unsafe integer numbers; convert the number input to bigint first.',
  });
  assert.throws(() => add(1n, oversizedNumber), {
    name: 'RangeError',
    message: 'Cannot mix bigint values with unsafe integer numbers; convert the number input to bigint first.',
  });
  assert.throws(() => add(oversizedNegativeNumber, 1n), {
    name: 'RangeError',
    message: 'Cannot mix bigint values with unsafe integer numbers; convert the number input to bigint first.',
  });
  assert.throws(() => add(1n, oversizedNegativeNumber), {
    name: 'RangeError',
    message: 'Cannot mix bigint values with unsafe integer numbers; convert the number input to bigint first.',
  });
});

test('add keeps existing single-value and empty-call behavior', () => {
  assert.equal(add(), 0);
  assert.equal(add(-0), 0);
  assert.equal(add.apply(null, [5]), 5);
  assert.equal(add(5n), 5n);
  assert.equal(add(Number.MAX_SAFE_INTEGER), Number.MAX_SAFE_INTEGER);
  assert.equal(add(0n), 0n);
});

test('add normalizes object operands at the public entrypoint', () => {
  const numericObject = {
    valueOf() {
      return 5;
    },
  };

  assert.equal(add(numericObject), 5);
  assert.equal(add(numericObject, 2), 7);
});

test('add unwraps value-wrapped operands before normalization', () => {
  const wrappedLeft = { value: { value: 2 } };
  const wrappedRight = { value: 3 };

  assert.equal(add(wrappedLeft, wrappedRight), 5);
});

test('add rejects string-like operands for single-value calls', () => {
  const boxedString = vm.runInNewContext('Object("2")');

  assert.throws(() => add('2'), {
    name: 'TypeError',
    message: 'add() does not accept string operands.',
  });
  assert.throws(() => add(boxedString), {
    name: 'TypeError',
    message: 'add() does not accept string operands.',
  });
});

test('add supports variadic invocation helpers without changing promotion rules', () => {
  const overflowingInputs = [0, Number.MAX_SAFE_INTEGER, 2];
  const mixedInputs = [1n, 2, 3, 4];

  assert.equal(add.apply(null, []), 0);
  assert.equal(add.apply(null, overflowingInputs), 9007199254740993n);
  assert.equal(add.apply(null, mixedInputs), 10n);
  assert.equal(add.call(null), 0);
  assert.equal(add.call(null, ...overflowingInputs), 9007199254740993n);
  assert.equal(add.call(null, ...mixedInputs), 10n);
});

test('add.call keeps number semantics after safe-range cancellation from a prior overflow boundary', () => {
  assert.equal(add.call(null, Number.MAX_SAFE_INTEGER, 1, -1), Number.MAX_SAFE_INTEGER);
  assert.equal(typeof add.call(null, Number.MAX_SAFE_INTEGER, 1, -1), 'number');
});

test('add preserves two-operand promotion rules through spread invocation', () => {
  const pairInputs = [Number.MAX_SAFE_INTEGER, 2];

  assert.equal(add(...pairInputs), 9007199254740993n);
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

test('add rejects bigint accumulation after integer number rounding inputs', () => {
  const oversizedNumber = Number.MAX_SAFE_INTEGER + 2;

  assert.throws(() => add(oversizedNumber, 1n, -1n), {
    name: 'RangeError',
    message: 'Cannot mix bigint values with unsafe integer numbers; convert the number input to bigint first.',
  });
});

test('add preserves bigint promotion after a zero-prefixed safe integer boundary', () => {
  assert.equal(add(0, Number.MAX_SAFE_INTEGER - 1, 1, 1), 9007199254740992n);
});

test('add rejects bigint semantics when an oversized number starts the list', () => {
  const oversizedNumber = Number.MAX_SAFE_INTEGER + 2;

  assert.throws(() => add(0n, oversizedNumber, -1n), {
    name: 'RangeError',
    message: 'Cannot mix bigint values with unsafe integer numbers; convert the number input to bigint first.',
  });
});

test('add rejects an oversized leading number once a later bigint appears', () => {
  const oversizedNumber = Number.MAX_SAFE_INTEGER + 2;

  assert.throws(() => add(oversizedNumber, 1n, 1), {
    name: 'RangeError',
    message: 'Cannot mix bigint values with unsafe integer numbers; convert the number input to bigint first.',
  });
});

test('add keeps a leading negative zero normalized before bigint promotion', () => {
  assert.equal(add(-0, 1n, -1), 0n);
});

test('add never returns negative zero for normalized number results', () => {
  assert.equal(Object.is(add(-0), -0), false);
  assert.equal(Object.is(add(-0, -0), -0), false);
  assert.equal(Object.is(add(-0, 0, 0), -0), false);
});

test('add rejects an oversized integer when a later bigint would promote the sum', () => {
  const oversizedNumber = Number.MAX_SAFE_INTEGER + 2;

  assert.throws(() => add(oversizedNumber, 0, 1n), {
    name: 'RangeError',
    message: 'Cannot mix bigint values with unsafe integer numbers; convert the number input to bigint first.',
  });
});

test('add preserves negative-zero normalization before rejecting bigint promotion', () => {
  const oversizedNumber = Number.MAX_SAFE_INTEGER + 2;

  assert.throws(() => add(oversizedNumber, -0, 1n), {
    name: 'RangeError',
    message: 'Cannot mix bigint values with unsafe integer numbers; convert the number input to bigint first.',
  });
});

test('add rejects a later bigint even if earlier unsafe integer rounding returns to safety', () => {
  const oversizedNumber = Number.MAX_SAFE_INTEGER + 2;

  assert.throws(() => add(oversizedNumber, -1, 1n), {
    name: 'RangeError',
    message: 'Cannot mix bigint values with unsafe integer numbers; convert the number input to bigint first.',
  });
});

test('add rejects unsafe integers after a variadic overflow boundary promoted the sum', () => {
  assert.throws(
    () => add(0, Number.MAX_SAFE_INTEGER, 1, Number.MAX_SAFE_INTEGER + 1),
    {
      name: 'RangeError',
      message: 'Cannot mix a variadic bigint-overflow sum with unsafe integer numbers; convert the number input to bigint first.',
    },
  );
});

test('add keeps that overflow-boundary guard after later bigint operands', () => {
  assert.throws(
    () => add(0, Number.MAX_SAFE_INTEGER, 1, 1n, Number.MAX_SAFE_INTEGER + 1),
    {
      name: 'RangeError',
      message: 'Cannot mix a variadic bigint-overflow sum with unsafe integer numbers; convert the number input to bigint first.',
    },
  );
});

test('add keeps the overflow-boundary guard on negative sums after returning near safety', () => {
  assert.throws(
    () => add(0, Number.MIN_SAFE_INTEGER, -1, 1, Number.MIN_SAFE_INTEGER - 1),
    {
      name: 'RangeError',
      message: 'Cannot mix a variadic bigint-overflow sum with unsafe integer numbers; convert the number input to bigint first.',
    },
  );
});

test('add returns to number semantics when negative inputs bring an overflow-promoted sum back to safety', () => {
  assert.equal(add(0, Number.MIN_SAFE_INTEGER, -1, 1), Number.MIN_SAFE_INTEGER);
  assert.equal(typeof add(0, Number.MIN_SAFE_INTEGER, -1, 1), 'number');
});

test('add returns to number semantics when positive inputs bring an overflow-promoted sum back to safety', () => {
  assert.equal(add(0, Number.MAX_SAFE_INTEGER, 1, -1), Number.MAX_SAFE_INTEGER);
  assert.equal(typeof add(0, Number.MAX_SAFE_INTEGER, 1, -1), 'number');
});

test('add keeps zero and mixed-sign overflow cancellation on number semantics', () => {
  assert.equal(
    add(0, Number.MAX_SAFE_INTEGER, 1, -1, 0),
    Number.MAX_SAFE_INTEGER,
  );
  assert.equal(
    typeof add(0, Number.MAX_SAFE_INTEGER, 1, -1, 0),
    'number',
  );
  assert.equal(
    add(0, Number.MIN_SAFE_INTEGER, -1, 1, 0),
    Number.MIN_SAFE_INTEGER,
  );
  assert.equal(
    typeof add(0, Number.MIN_SAFE_INTEGER, -1, 1, 0),
    'number',
  );
});

const assert = require('assert');
const { add } = require('../src/lib/add');

const expectFiniteInputError = /add expects finite numeric inputs/;

assert.strictEqual(add(1, 2), 3);
assert.strictEqual(add('2', '5'), 7);
assert.strictEqual(add(' 2 ', '\t5\n'), 7);
assert.strictEqual(
  add({ value: ' 2 ' }, { value: 5 }),
  7,
);
assert.strictEqual(
  add({ value: { value: { value: ' 3 ' } } }, { value: { value: ' 4 ' } }),
  7,
);
assert.strictEqual(
  add(
    {
      valueOf() {
        return ' 5 ';
      },
      toString() {
        throw new Error('should not be called');
      },
    },
    2,
  ),
  7,
);
assert.strictEqual(
  add(
    {
      valueOf() {
        return {};
      },
      toString() {
        return ' 6 ';
      },
    },
    1,
  ),
  7,
);
assert.strictEqual(
  add(
    {
      valueOf() {
        return {};
      },
      [Symbol.toPrimitive]() {
        return ' 8 ';
      },
    },
    2,
  ),
  10,
);
assert.throws(
  () => add('', 2),
  expectFiniteInputError
);
assert.throws(
  () => add('   ', 2),
  expectFiniteInputError
);
assert.throws(
  () => add('nope', 2),
  expectFiniteInputError
);
assert.throws(
  () => add(true, 2),
  expectFiniteInputError
);
assert.throws(
  () => add(null, 2),
  expectFiniteInputError
);
assert.throws(
  () => add(undefined, 2),
  expectFiniteInputError
);
assert.throws(
  () => add({ value: {} }, 1),
  expectFiniteInputError
);

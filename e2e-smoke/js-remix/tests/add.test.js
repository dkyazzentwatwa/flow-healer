const assert = require('assert');
const { add } = require('../app/utils/add.server');

const expectFiniteInputError = {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
};

assert.strictEqual(add(1, 2), 3);
assert.strictEqual(add('2', '5'), 7);
assert.strictEqual(add(' 2 ', ' 5 '), 7);
assert.strictEqual(add({ value: '4' }, 3), 7);
assert.strictEqual(add({ value: { value: '4' } }, 3), 7);
assert.throws(() => add('nope', 1), expectFiniteInputError);
assert.throws(() => add('   ', 1), expectFiniteInputError);
assert.throws(() => add(true, 1), expectFiniteInputError);
assert.throws(() => add({ value: 'nope' }, 1), expectFiniteInputError);
assert.throws(() => add({ value: { value: 'nope' } }, 1), expectFiniteInputError);

assert.strictEqual(
  add({ valueOf() { return 4; } }, { value: '3' }),
  7,
);

assert.strictEqual(
  add({ value: { toString() { return ' 5 '; } } }, { value: { valueOf() { return '2'; } } }),
  7,
);

assert.strictEqual(
  add(
    {
      [Symbol.toPrimitive]() {
        return '  6 ';
      },
    },
    1,
  ),
  7,
);

assert.throws(
  () => add(
    {
      [Symbol.toPrimitive]() {
        return {};
      },
    },
    1,
  ),
  expectFiniteInputError,
);

const assert = require('assert');
const { add, addMany } = require('../src/add');

const expectFiniteInputError = {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
};

assert.strictEqual(add(1, 2), 3);
assert.strictEqual(add('2', '5'), 7);
assert.strictEqual(addMany(1, 2, 3), 6);
assert.strictEqual(addMany('4', '5', '6'), 15);
assert.strictEqual(addMany(1, 2, 3, 4), 10);
assert.strictEqual(addMany(' 1 ', '\n2\t', 3, ' 4 '), 10);
assert.strictEqual(addMany(), 0);
assert.strictEqual(addMany(5), 5);
assert.strictEqual(addMany(5, 7), 12);
assert.throws(() => addMany('oops', 5, 6), expectFiniteInputError);
assert.throws(() => addMany(1, 2, 'oops', 6), expectFiniteInputError);
assert.throws(() => add(null, 5), expectFiniteInputError);
assert.throws(() => add('', 5), expectFiniteInputError);
assert.throws(() => add('two', 5), expectFiniteInputError);
assert.strictEqual(
  add({ value: ' 2 ' }, { value: 5 }),
  7,
);
assert.strictEqual(
  add({ value: { value: { value: '  3 ' } } }, { value: { value: ' 4 ' } }),
  7,
);
assert.strictEqual(
  addMany(
    { value: '1' },
    { value: { value: '2' } },
    { value: 3 },
    { value: { value: ' 4 ' } },
  ),
  10,
);
assert.throws(() => add({ value: 'oops' }, 5), expectFiniteInputError);
assert.throws(() => addMany({ value: 'oops' }, 5, 6), expectFiniteInputError);

const assert = require('assert');
const { add } = require('../src/add');

function createFunctionWrapper(value) {
  const wrapper = () => value;
  wrapper.value = value;
  return wrapper;
}

assert.strictEqual(add(1, 2), 3);
assert.strictEqual(add('2', '5'), 7);
assert.strictEqual(add(' 2 ', '\t5\n'), 7);
assert.strictEqual(add({ value: '2' }, { value: 5 }), 7);
assert.strictEqual(
  add({ value: { value: '  2 ' } }, { value: { value: '\t5\n' } }),
  7,
);
assert.strictEqual(add({ value: { value: 3 } }, 4), 7);
const leftFunctionWrapper = createFunctionWrapper('  2 ');
const rightFunctionWrapper = createFunctionWrapper('\t5\n');
assert.strictEqual(add(leftFunctionWrapper, { value: 5 }), 7);
assert.strictEqual(
  add({ value: leftFunctionWrapper }, { value: rightFunctionWrapper }),
  7,
);

const expectFiniteInputError = {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
};

assert.throws(() => add('', 5), expectFiniteInputError);
assert.throws(() => add('   ', 5), expectFiniteInputError);
assert.throws(() => add('two', 5), expectFiniteInputError);
assert.throws(() => add({ value: 'two' }, 5), expectFiniteInputError);
assert.throws(() => add({ value: { value: 'two' } }, 5), expectFiniteInputError);
assert.throws(() => add({ value: { value: '   ' } }, 5), expectFiniteInputError);
const invalidFunctionWrapper = createFunctionWrapper('two');
assert.throws(() => add(invalidFunctionWrapper, 5), expectFiniteInputError);
assert.throws(() => add({ value: invalidFunctionWrapper }, 5), expectFiniteInputError);
assert.throws(() => add(null, 5), expectFiniteInputError);
assert.throws(() => add({ value: null }, 5), expectFiniteInputError);
assert.throws(() => add(true, 5), expectFiniteInputError);
assert.throws(() => add({ value: { value: true } }, 5), expectFiniteInputError);
assert.throws(() => add(Infinity, 5), expectFiniteInputError);
assert.throws(() => add({ value: Infinity }, 5), expectFiniteInputError);

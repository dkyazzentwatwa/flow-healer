const assert = require('assert');
const { add } = require('../src/utils/add');

assert.strictEqual(add(1, 2), 3);
assert.strictEqual(add('2', '5'), 7);
assert.strictEqual(add(' 2 ', ' 5 '), 7);
assert.strictEqual(add({ value: '4' }, 3), 7);
assert.strictEqual(
  add({ value: { value: ' 2 ' } }, { value: { value: 5 } }),
  7,
);
assert.throws(() => add('two', 5), {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
});
assert.throws(() => add('   ', 5), {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
});
assert.throws(() => add('', 5), {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
});
assert.throws(() => add(true, 5), {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
});
assert.throws(() => add(null, 5), {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
});
assert.throws(() => add(Infinity, 5), {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
});
assert.throws(() => add({ value: 'nope' }, 1), {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
});
assert.throws(() => add({ value: { value: 'nope' } }, 1), {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
});

const assert = require('assert');
const { add } = require('../src/add');

assert.strictEqual(add(1, 2), 3);
assert.strictEqual(add('2', '5'), 7);
assert.strictEqual(add({ value: '2' }, { value: '5' }), 7);
assert.strictEqual(add({ value: { value: '7' } }, { value: '5' }), 12);
assert.throws(() => add('', 5), {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
});
assert.throws(
  () => add({ value: 'two' }, 1),
  {
    name: 'TypeError',
    message: 'add expects finite numeric inputs',
  },
);
assert.throws(() => add('two', 5), {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
});
assert.throws(() => add(true, 5), {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
});

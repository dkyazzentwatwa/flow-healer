const assert = require('assert');
const { add } = require('../src/add');

assert.strictEqual(add(1, 2), 3);
assert.strictEqual(add('2', '5'), 7);
assert.strictEqual(add(' 2 ', ' 5 '), 7);
assert.strictEqual(add({ value: '4' }, 3), 7);
assert.throws(
  () => add('   ', 1),
  {
    name: 'TypeError',
    message: 'add expects finite numeric inputs',
  }
);
assert.throws(
  () => add(true, 1),
  {
    name: 'TypeError',
    message: 'add expects finite numeric inputs',
  }
);
assert.throws(
  () => add('nope', 1),
  {
    name: 'TypeError',
    message: 'add expects finite numeric inputs',
  }
);
assert.throws(
  () => add({ value: 'nope' }, 1),
  {
    name: 'TypeError',
    message: 'add expects finite numeric inputs',
  }
);

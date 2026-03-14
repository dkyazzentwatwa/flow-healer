const assert = require('assert');
const { add } = require('../src/add');

assert.strictEqual(add(1, 2), 3);
assert.strictEqual(add('2', '5'), 7);
assert.strictEqual(add({ value: '2' }, { value: '5' }), 7);
assert.throws(
  () => add({ value: 'two' }, 1),
  new TypeError('add expects finite numeric inputs')
);
assert.throws(
  () => add('', 5),
  new TypeError('add expects finite numeric inputs')
);
assert.throws(
  () => add('nope', 1),
  new TypeError('add expects finite numeric inputs')
);
assert.throws(
  () => add(true, 2),
  new TypeError('add expects finite numeric inputs')
);
assert.throws(
  () => add(null, 2),
  new TypeError('add expects finite numeric inputs')
);

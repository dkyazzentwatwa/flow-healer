const assert = require('assert');
const { add } = require('../src/add');

assert.strictEqual(add(1, 2), 3);
assert.strictEqual(add('2', '5'), 7);
assert.strictEqual(add(' 2 ', ' 5 '), 7);
assert.throws(() => add('nope', 1), {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
});
assert.throws(() => add('   ', 1), {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
});
assert.throws(() => add(true, 2), {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
});
assert.throws(() => add(null, 2), {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
});

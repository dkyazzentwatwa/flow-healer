const assert = require('assert');
const { add, addMany } = require('../src/add');

assert.strictEqual(add(1, 2), 3);
assert.strictEqual(add('2', '5'), 7);
assert.strictEqual(addMany(1, 2, 3), 6);
assert.strictEqual(addMany('4', '5', '6'), 15);
assert.throws(() => addMany('oops', 5, 6), {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
});
assert.throws(() => add(null, 5), {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
});
assert.throws(() => add('', 5), {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
});
assert.throws(() => add('two', 5), {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
});

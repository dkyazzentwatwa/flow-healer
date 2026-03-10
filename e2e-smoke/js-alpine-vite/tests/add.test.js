const assert = require('assert');
const { add } = require('../src/add');

assert.strictEqual(add(1, 2), 3);
assert.strictEqual(add('2', '5'), 7);
assert.strictEqual(add(' 2 ', '\t5\n'), 7);
assert.throws(
  () => add('', 1),
  /add expects finite numeric inputs/,
);
assert.throws(
  () => add('   ', 1),
  /add expects finite numeric inputs/,
);
assert.throws(
  () => add('nope', 1),
  /add expects finite numeric inputs/,
);
assert.throws(
  () => add(Infinity, 1),
  /add expects finite numeric inputs/,
);

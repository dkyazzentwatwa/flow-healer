const assert = require('assert');
const { add } = require('../src/lib/add');

assert.strictEqual(add(1, 2), 3);
assert.strictEqual(add('2', '5'), 7);
assert.strictEqual(add(' 2 ', '\t5\n'), 7);
assert.throws(
  () => add('', 2),
  /add expects finite numeric inputs/
);
assert.throws(
  () => add('   ', 2),
  /add expects finite numeric inputs/
);
assert.throws(
  () => add('nope', 2),
  /add expects finite numeric inputs/
);
assert.throws(
  () => add(true, 2),
  /add expects finite numeric inputs/
);
assert.throws(
  () => add(null, 2),
  /add expects finite numeric inputs/
);
assert.throws(
  () => add(undefined, 2),
  /add expects finite numeric inputs/
);

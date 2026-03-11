const assert = require('assert');
const { add } = require('../app/services/add.ts');

assert.strictEqual(add(1, 2), 3);
assert.strictEqual(add('2', '5'), 7);
assert.throws(
  () => add('   ', 1),
  /add expects finite numeric inputs/
);
assert.throws(
  () => add(true as unknown as number, 1),
  /add expects finite numeric inputs/
);
assert.throws(
  () => add('nope', 1),
  /add expects finite numeric inputs/
);

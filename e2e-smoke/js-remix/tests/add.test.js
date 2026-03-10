const assert = require('assert');
const { add } = require('../app/utils/add.server');

assert.strictEqual(add(1, 2), 3);
assert.strictEqual(add('2', '5'), 7);

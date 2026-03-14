const assert = require('assert');
const { add, handler } = require('../src/add');

assert.strictEqual(add(1, 2), 3);
assert.strictEqual(add('2', '5'), 7);
assert.strictEqual(add(' 2 ', '\t5\n'), 7);
assert.throws(() => add('', 5), {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
});
assert.throws(() => add('   ', 5), {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
});
assert.throws(() => add('two', 5), {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
});

const successContext = createContext({ a: '4', b: '6' });
assert.deepStrictEqual(handler(successContext), {
  body: { result: 10 },
  status: 200,
});

const invalidContext = createContext({ a: 'two', b: '6' });
assert.deepStrictEqual(handler(invalidContext), {
  body: { error: 'add expects finite numeric inputs' },
  status: 400,
});

const fallbackContext = {
  req: {
    query() {
      return { a: '4', b: '6' };
    },
  },
  json(body, status = 200) {
    return { body, status };
  },
};

assert.deepStrictEqual(handler(fallbackContext), {
  body: { result: 10 },
  status: 200,
});

function createContext(query) {
  return {
    req: {
      query(name) {
        return query[name];
      },
    },
    json(body, status = 200) {
      return { body, status };
    },
  };
}

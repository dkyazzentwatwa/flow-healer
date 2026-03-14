const assert = require('assert');
const {
  add,
  handler,
  addHandler,
  middleware,
  addMiddleware,
  handleAdd,
} = require('../src/add');

assert.strictEqual(add(1, 2), 3);
assert.strictEqual(add('2', '5'), 7);
assert.strictEqual(add(' 2 ', ' 5 '), 7);
assert.throws(() => add('two', 5), {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
});
assert.throws(() => add('', '5'), {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
});
assert.throws(() => add(true, 5), {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
});

assert.strictEqual(handler, addHandler);
assert.strictEqual(handler, middleware);
assert.strictEqual(handler, addMiddleware);
assert.strictEqual(handler, handleAdd);

assert.deepStrictEqual(executeHandler(handler, { a: '4', b: '6' }), {
  status: 200,
  body: { result: 10 },
});

assert.deepStrictEqual(executeHandler(handler, { a: 'two', b: '6' }), {
  status: 400,
  body: { error: 'add expects finite numeric inputs' },
});

assert.deepStrictEqual(executeHandler(addHandler, { a: '4', b: '6' }), {
  status: 200,
  body: { result: 10 },
});

function executeHandler(handlerFn, query) {
  const res = {
    _statusCode: 200,
    status(code) {
      this._statusCode = code;
      return this;
    },
    json(payload) {
      return {
        status: this._statusCode,
        body: payload,
      };
    },
  };

  return handlerFn({ query }, res);
}

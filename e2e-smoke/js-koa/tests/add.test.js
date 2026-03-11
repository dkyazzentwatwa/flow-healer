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
assert.strictEqual(add(' 2 ', '\t5\n'), 7);
assert.throws(() => add('two', 5), {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
});
assert.throws(() => add('', 5), {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
});
assert.throws(() => add(true, 5), {
  name: 'TypeError',
  message: 'add expects finite numeric inputs',
});

Promise.all([
  expectMiddlewareResult(handler, { a: '4', b: '6' }, { body: { result: 10 } }),
  expectMiddlewareResult(addHandler, { a: '4', b: '6' }, { body: { result: 10 } }),
  expectMiddlewareResult(handleAdd, { a: '4', b: '6' }, { body: { result: 10 } }),
  expectMiddlewareResult(middleware, { a: 'two', b: '6' }, {
    body: { error: 'add expects finite numeric inputs' },
    status: 400,
  }),
  expectMiddlewareResult(addMiddleware, { a: 'two', b: '6' }, {
    body: { error: 'add expects finite numeric inputs' },
    status: 400,
  }),
]).catch((error) => {
  process.exitCode = 1;
  throw error;
});

async function expectMiddlewareResult(fn, query, expected) {
  assert.strictEqual(typeof fn, 'function');

  const context = { query };
  let nextCalled = false;

  await fn(context, async () => {
    nextCalled = true;
  });

  assert.strictEqual(nextCalled, true);
  assert.deepStrictEqual(context.body, expected.body);
  assert.strictEqual(context.status ?? 200, expected.status ?? 200);
}

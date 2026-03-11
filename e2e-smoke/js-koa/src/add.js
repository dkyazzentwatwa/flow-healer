function add(a, b) {
  const left = normalizeFiniteNumber(a);
  const right = normalizeFiniteNumber(b);

  return left + right;
}

async function handler(context, next) {
  try {
    context.body = {
      result: add(getQueryValue(context, 'a'), getQueryValue(context, 'b')),
    };
  } catch (error) {
    if (!(error instanceof TypeError)) {
      throw error;
    }

    context.status = 400;
    context.body = { error: error.message };
  }

  if (typeof next === 'function') {
    await next();
  }
}

function getQueryValue(context, name) {
  if (!context || !context.query || typeof context.query !== 'object') {
    return undefined;
  }

  return context.query[name];
}

function normalizeFiniteNumber(value) {
  if (typeof value === 'string') {
    const trimmed = value.trim();

    if (trimmed === '') {
      throw new TypeError('add expects finite numeric inputs');
    }

    value = Number(trimmed);
  } else if (typeof value !== 'number') {
    throw new TypeError('add expects finite numeric inputs');
  }

  if (!Number.isFinite(value)) {
    throw new TypeError('add expects finite numeric inputs');
  }

  return value;
}

module.exports = {
  add,
  handler,
  addHandler: handler,
  middleware: handler,
  addMiddleware: handler,
  handleAdd: handler,
};

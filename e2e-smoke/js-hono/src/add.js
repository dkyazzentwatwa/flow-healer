function add(a, b) {
  const left = toFiniteNumber(a);
  const right = toFiniteNumber(b);

  if (!Number.isFinite(left) || !Number.isFinite(right)) {
    throw new TypeError('add expects finite numeric inputs');
  }

  return left + right;
}

function handler(context) {
  try {
    const result = add(
      getQueryValue(context, 'a'),
      getQueryValue(context, 'b'),
    );

    return json(context, { result });
  } catch (error) {
    if (error instanceof TypeError) {
      return json(context, { error: error.message }, 400);
    }

    throw error;
  }
}

function getQueryValue(context, name) {
  const request = context && context.req;

  if (!request) {
    return undefined;
  }

  if (typeof request.query === 'function') {
    const value = request.query(name);

    if (value !== undefined && typeof value !== 'object') {
      return value;
    }

    const query = request.query();

    if (query && typeof query === 'object') {
      return query[name];
    }
  }

  if (request.query && typeof request.query === 'object') {
    return request.query[name];
  }

  if (request.url) {
    return new URL(request.url, 'http://localhost').searchParams.get(name);
  }

  return undefined;
}

function json(context, body, status = 200) {
  if (context && typeof context.json === 'function') {
    return context.json(body, status);
  }

  return new Response(JSON.stringify(body), {
    headers: { 'content-type': 'application/json; charset=utf-8' },
    status,
  });
}

function toFiniteNumber(value) {
  if (value === null || typeof value === 'boolean') {
    return Number.NaN;
  }

  if (typeof value === 'string') {
    const trimmed = value.trim();

    if (trimmed === '') {
      return Number.NaN;
    }

    return Number(trimmed);
  }

  return Number(value);
}

module.exports = { add, handler, addHandler: handler, handleAdd: handler };

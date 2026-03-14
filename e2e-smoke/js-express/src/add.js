function sendJsonPayload(response, body, statusCode) {
  if (!response) {
    return { status: statusCode, body };
  }

  if (typeof response.status === 'function') {
    const statusResponse = response.status(statusCode);

    if (statusResponse && typeof statusResponse.json === 'function') {
      statusResponse.json(body);
      return { status: statusCode, body };
    }

    if (statusResponse && typeof statusResponse.send === 'function') {
      statusResponse.send(body);
      return { status: statusCode, body };
    }
  }

  if (typeof response.json === 'function') {
    if (!Number.isFinite(response.statusCode)) {
      response.statusCode = statusCode;
    }

    response.json(body);
    return { status: response.statusCode, body };
  }

  if (typeof response.send === 'function') {
    if (!Number.isFinite(response.statusCode)) {
      response.statusCode = statusCode;
    }

    response.send(body);
    return { status: response.statusCode, body };
  }

  response.body = body;
  response.statusCode = statusCode;
  return { status: statusCode, body };
}

function add(a, b) {
  const left = normalizeFiniteNumber(a);
  const right = normalizeFiniteNumber(b);

  return left + right;
}

function handler(req, res) {
  try {
    return sendJsonPayload(
      res,
      {
        result: add(
          getQueryValue(req, 'a'),
          getQueryValue(req, 'b'),
        ),
      },
      200,
    );
  } catch (error) {
    if (!(error instanceof TypeError)) {
      throw error;
    }

    return sendJsonPayload(res, { error: error.message }, 400);
  }
}

function getQueryValue(req, name) {
  if (!req || typeof req !== 'object' || !req.query || typeof req.query !== 'object') {
    return undefined;
  }

  return req.query[name];
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
  addMiddleware: handler,
  middleware: handler,
  handleAdd: handler,
};

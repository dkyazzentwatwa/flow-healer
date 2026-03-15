const EXPECTED_ERROR_MESSAGE = 'add expects finite numeric inputs';

function add(a, b) {
  const left = normalizeFiniteNumber(a);
  const right = normalizeFiniteNumber(b);

  return left + right;
}

function normalizeFiniteNumber(value) {
  const primitive = toPrimitiveValue(unwrapValue(value));

  return convertPrimitiveToFiniteNumber(primitive);
}

function unwrapValue(value) {
  while (value && typeof value === 'object' && 'value' in value) {
    value = value.value;
  }

  return value;
}

function toPrimitiveValue(value) {
  if (isPrimitive(value)) {
    return value;
  }

  const primitive = trySymbolToPrimitive(value);
  if (primitive !== undefined && isPrimitive(primitive)) {
    return primitive;
  }

  return ordinaryToPrimitive(value);
}

function trySymbolToPrimitive(value) {
  if (value == null) {
    return value;
  }

  const toPrimitive = value[Symbol.toPrimitive];

  if (typeof toPrimitive !== 'function') {
    return undefined;
  }

  return toPrimitive.call(value, 'default');
}

function ordinaryToPrimitive(value) {
  for (const method of ['valueOf', 'toString']) {
    const coerced = value[method];

    if (typeof coerced !== 'function') {
      continue;
    }

    const result = coerced.call(value);

    if (isPrimitive(result)) {
      return result;
    }
  }

  throwFiniteInputError();
}

function isPrimitive(value) {
  return value === null || (typeof value !== 'object' && typeof value !== 'function');
}

function convertPrimitiveToFiniteNumber(value) {
  if (typeof value === 'string') {
    const trimmed = value.trim();

    if (trimmed === '') {
      throwFiniteInputError();
    }

    value = Number(trimmed);
  } else if (typeof value !== 'number') {
    throwFiniteInputError();
  }

  if (!Number.isFinite(value)) {
    throwFiniteInputError();
  }

  return value;
}

function throwFiniteInputError() {
  throw new TypeError(EXPECTED_ERROR_MESSAGE);
}

module.exports = { add };

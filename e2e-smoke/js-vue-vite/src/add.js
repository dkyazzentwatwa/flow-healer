const FINITE_INPUT_ERROR_MESSAGE = 'add expects finite numeric inputs';

function add(a, b) {
  const left = toFiniteNumber(a);
  const right = toFiniteNumber(b);

  return left + right;
}

function toFiniteNumber(value) {
  value = unwrapValue(value);

  if (typeof value === 'string') {
    const trimmed = value.trim();

    if (trimmed === '') {
      throw new TypeError(FINITE_INPUT_ERROR_MESSAGE);
    }

    value = Number(trimmed);
  } else if (typeof value !== 'number') {
    throw new TypeError(FINITE_INPUT_ERROR_MESSAGE);
  }

  if (!Number.isFinite(value)) {
    throw new TypeError(FINITE_INPUT_ERROR_MESSAGE);
  }

  return value;
}

function unwrapValue(value) {
  while (isValueWrapper(value)) {
    value = value.value;
  }

  return value;
}

function isValueWrapper(value) {
  if (value === null) {
    return false;
  }

  const valueType = typeof value;
  return (valueType === 'object' || valueType === 'function') && 'value' in value;
}

module.exports = { add };

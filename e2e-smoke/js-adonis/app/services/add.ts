const FINITE_NUMERIC_INPUT_ERROR = 'add expects finite numeric inputs';

function add(a: unknown, b: unknown): number {
  const left = normalizeFiniteNumber(a);
  const right = normalizeFiniteNumber(b);

  return left + right;
}

function normalizeFiniteNumber(value: unknown): number {
  let normalizedValue: unknown = unwrapValue(value);

  let numericValue: number;

  if (typeof normalizedValue === 'string') {
    const trimmed = normalizedValue.trim();

    if (trimmed === '') {
      throw new TypeError(FINITE_NUMERIC_INPUT_ERROR);
    }

    numericValue = Number(trimmed);
  } else if (typeof normalizedValue === 'number') {
    numericValue = normalizedValue;
  } else {
    throw new TypeError(FINITE_NUMERIC_INPUT_ERROR);
  }

  if (!Number.isFinite(numericValue)) {
    throw new TypeError(FINITE_NUMERIC_INPUT_ERROR);
  }

  return numericValue;
}

function unwrapValue(value: unknown): unknown {
  let current: unknown = value;

  while (
    current !== null
    && typeof current === 'object'
    && 'value' in current
  ) {
    current = (current as { value: unknown }).value;
  }

  return current;
}

module.exports = { add };

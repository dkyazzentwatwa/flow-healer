const FINITE_NUMERIC_INPUT_ERROR = 'add expects finite numeric inputs';

function add(a: number | string, b: number | string): number {
  const left = normalizeFiniteNumber(a);
  const right = normalizeFiniteNumber(b);

  return left + right;
}

function normalizeFiniteNumber(value: number | string): number {
  if (typeof value === 'string') {
    const trimmed = value.trim();

    if (trimmed === '') {
      throw new TypeError(FINITE_NUMERIC_INPUT_ERROR);
    }

    value = Number(trimmed);
  } else if (typeof value !== 'number') {
    throw new TypeError(FINITE_NUMERIC_INPUT_ERROR);
  }

  if (!Number.isFinite(value)) {
    throw new TypeError(FINITE_NUMERIC_INPUT_ERROR);
  }

  return value;
}

module.exports = { add };

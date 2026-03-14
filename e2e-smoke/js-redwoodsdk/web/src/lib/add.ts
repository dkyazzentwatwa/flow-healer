const FINITE_NUMERIC_INPUT_ERROR = 'add expects finite numeric inputs';

function add(a: unknown, b: unknown): number {
  const normalize = (value: unknown): number => {
    while (value && typeof value === 'object' && 'value' in value) {
      value = (value as { value: unknown }).value;
    }

    if (typeof value === 'string') {
      const trimmed = value.trim();

      if (trimmed === '') {
        throw new TypeError(FINITE_NUMERIC_INPUT_ERROR);
      }

      return Number(trimmed);
    }

    if (typeof value !== 'number') {
      throw new TypeError(FINITE_NUMERIC_INPUT_ERROR);
    }

    return value;
  };

  const left = normalize(a);
  const right = normalize(b);

  if (!Number.isFinite(left) || !Number.isFinite(right)) {
    throw new TypeError(FINITE_NUMERIC_INPUT_ERROR);
  }

  return left + right;
}

module.exports = { add };

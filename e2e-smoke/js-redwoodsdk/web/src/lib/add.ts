function add(a: number | string, b: number | string): number {
  const normalize = (value: number | string): number => {
    if (typeof value === 'string') {
      const trimmed = value.trim();

      if (trimmed === '') {
        return Number.NaN;
      }

      return Number(trimmed);
    }

    return Number(value);
  };

  const left = normalize(a);
  const right = normalize(b);

  if (!Number.isFinite(left) || !Number.isFinite(right)) {
    throw new TypeError('add expects finite numeric inputs');
  }

  return left + right;
}

module.exports = { add };

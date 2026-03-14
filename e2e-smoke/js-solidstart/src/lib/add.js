function add(a, b) {
  const left = toFiniteNumber(a);
  const right = toFiniteNumber(b);

  if (!Number.isFinite(left) || !Number.isFinite(right)) {
    throw new TypeError('add expects finite numeric inputs');
  }

  return left + right;
}

function toFiniteNumber(value) {
  if (typeof value === 'string') {
    const trimmed = value.trim();

    if (trimmed === '') {
      return Number.NaN;
    }

    return Number(trimmed);
  }

  if (typeof value !== 'number') {
    return Number.NaN;
  }

  return value;
}

module.exports = { add };

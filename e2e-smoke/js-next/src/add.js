function add(a, b) {
  const left = normalizeFiniteNumber(a);
  const right = normalizeFiniteNumber(b);

  return left + right;
}

function addMany(a, b, c) {
  return (
    normalizeFiniteNumber(a) +
    normalizeFiniteNumber(b) +
    normalizeFiniteNumber(c)
  );
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

module.exports = { add, addMany };

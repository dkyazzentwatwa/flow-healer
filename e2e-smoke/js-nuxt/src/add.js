function add(a, b) {
  const left = toFiniteNumber(a);
  const right = toFiniteNumber(b);

  return left + right;
}

function toFiniteNumber(value) {
  while (value && typeof value === 'object' && 'value' in value) {
    value = value.value;
  }

  if (typeof value === 'string') {
    const trimmed = value.trim();

    if (trimmed === '') {
      throw new TypeError('add expects finite numeric inputs');
    }

    value = Number(trimmed);
  }

  if (typeof value !== 'number') {
    throw new TypeError('add expects finite numeric inputs');
  }

  if (!Number.isFinite(value)) {
    throw new TypeError('add expects finite numeric inputs');
  }

  return value;
}

module.exports = { add };

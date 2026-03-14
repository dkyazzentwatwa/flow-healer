function add(a, b) {
  const left = toFiniteNumber(a);
  const right = toFiniteNumber(b);

  return left + right;
}

function toFiniteNumber(value) {
  if (value && typeof value === 'object' && 'value' in value) {
    value = value.value;
  } else if (value !== null && typeof value === 'object') {
    throw new TypeError('add expects finite numeric inputs');
  }

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

module.exports = { add };

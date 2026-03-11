function add(a, b) {
  const left = toFiniteNumber(a);
  const right = toFiniteNumber(b);

  return left + right;
}

function toFiniteNumber(value) {
  if (value && typeof value === 'object' && 'value' in value) {
    value = value.value;
  }

  if (typeof value === 'string') {
    const trimmed = value.trim();

    if (trimmed === '') {
      throw new TypeError('add expects finite numeric inputs');
    }

    value = trimmed;
  }

  const number = Number(value);

  if (!Number.isFinite(number)) {
    throw new TypeError('add expects finite numeric inputs');
  }

  return number;
}

module.exports = { add };

function add(a, b) {
  const left = normalizeFiniteNumber(a);
  const right = normalizeFiniteNumber(b);

  return left + right;
}

function addMany(...operands) {
  if (operands.length < 3) {
    throw new TypeError('add expects finite numeric inputs');
  }

  let total = 0;

  for (const operand of operands) {
    total += normalizeFiniteNumber(operand);
  }

  return total;
}

function unwrapValue(value) {
  while (value && typeof value === 'object' && 'value' in value) {
    value = value.value;
  }

  return value;
}

function normalizeFiniteNumber(value) {
  value = unwrapValue(value);
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

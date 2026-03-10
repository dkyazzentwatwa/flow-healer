function add(a, b) {
  const left = typeof a === 'string' ? Number(a.trim()) : Number(a);
  const right = typeof b === 'string' ? Number(b.trim()) : Number(b);

  if (
    (typeof a === 'string' && a.trim() === '')
    || (typeof b === 'string' && b.trim() === '')
    || !Number.isFinite(left)
    || !Number.isFinite(right)
  ) {
    throw new TypeError('add expects finite numeric inputs');
  }

  return left + right;
}

module.exports = { add };

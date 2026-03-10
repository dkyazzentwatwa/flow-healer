function add(a, b) {
  const left = Number(a);
  const right = Number(b);

  if (!Number.isFinite(left) || !Number.isFinite(right)) {
    throw new TypeError('add expects finite numeric inputs');
  }

  return left + right;
}

module.exports = { add };

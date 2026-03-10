function add(a: number | string, b: number | string): number {
  const left = Number(a);
  const right = Number(b);

  if (!Number.isFinite(left) || !Number.isFinite(right)) {
    throw new TypeError('add expects finite numeric inputs');
  }

  return left + right;
}

module.exports = { add };

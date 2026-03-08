export function add(a, b) {
  if (typeof a === 'bigint' && typeof b === 'bigint') {
    return a + b;
  }

  const sum = a + b;

  return sum === 0 ? 0 : sum;
}

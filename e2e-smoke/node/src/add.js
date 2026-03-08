function canPromoteToBigInt(value) {
  return typeof value === 'bigint' || Number.isSafeInteger(value);
}

function toBigInt(value) {
  return typeof value === 'bigint' ? value : BigInt(value);
}

function normalizeZero(sum) {
  return typeof sum === 'bigint'
    ? (sum === 0n ? 0n : sum)
    : (sum === 0 ? 0 : sum);
}

function addPair(a, b) {
  const canPromoteOperandsToBigInt =
    canPromoteToBigInt(a) && canPromoteToBigInt(b);

  if (canPromoteOperandsToBigInt) {
    const hasBigIntOperand = typeof a === 'bigint' || typeof b === 'bigint';

    if (hasBigIntOperand) {
      return normalizeZero(toBigInt(a) + toBigInt(b));
    }

    const numericSum = a + b;

    if (!Number.isSafeInteger(numericSum)) {
      return normalizeZero(toBigInt(a) + toBigInt(b));
    }
  }

  return normalizeZero(a + b);
}

function sumOperands(operands) {
  let accumulatedSum = addPair(operands[0], operands[1]);

  for (let index = 2; index < operands.length; index += 1) {
    accumulatedSum = addPair(accumulatedSum, operands[index]);
  }

  return accumulatedSum;
}

export function add(...operands) {
  const operandCount = operands.length;

  if (operandCount === 0) {
    return 0;
  }

  if (operandCount === 1) {
    return normalizeZero(operands[0]);
  }

  if (operandCount === 2) {
    return addPair(operands[0], operands[1]);
  }

  return sumOperands(operands);
}

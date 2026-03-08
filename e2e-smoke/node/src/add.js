function canPromoteToBigInt(value) {
  return typeof value === 'bigint' || Number.isSafeInteger(value);
}

function isUnsafeIntegerNumber(value) {
  return typeof value === 'number'
    && Number.isInteger(value)
    && !Number.isSafeInteger(value);
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
  const hasBigIntOperand = typeof a === 'bigint' || typeof b === 'bigint';

  if (hasBigIntOperand && (isUnsafeIntegerNumber(a) || isUnsafeIntegerNumber(b))) {
    throw new RangeError(
      'Cannot mix bigint values with unsafe integer numbers; convert the number input to bigint first.',
    );
  }

  const canPromoteOperandsToBigInt =
    canPromoteToBigInt(a) && canPromoteToBigInt(b);

  if (canPromoteOperandsToBigInt) {
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
  let accumulatedSum = normalizeZero(operands[0]);

  for (let index = 1; index < operands.length; index += 1) {
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

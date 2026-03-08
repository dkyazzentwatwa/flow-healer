function isIntegerNumber(value) {
  return typeof value === 'number' && Number.isFinite(value) && Number.isInteger(value);
}

function canConvertToBigInt(value) {
  return typeof value === 'bigint' || isIntegerNumber(value);
}

function toBigInt(value) {
  return typeof value === 'bigint' ? value : BigInt(value);
}

function normalizeZero(sum) {
  return typeof sum === 'bigint'
    ? (sum === 0n ? 0n : sum)
    : (sum === 0 ? 0 : sum);
}

function hasBigIntOperand(a, b) {
  return typeof a === 'bigint' || typeof b === 'bigint';
}

function getInitialAccumulatedSum(operands) {
  return normalizeZero(operands[0] ?? 0);
}

function shouldPromoteSafeIntegerSum(a, b, numericSum) {
  return Number.isSafeInteger(a)
    && Number.isSafeInteger(b)
    && !Number.isSafeInteger(numericSum);
}

function addPair(a, b) {
  const canPromoteOperandsToBigInt =
    canConvertToBigInt(a) && canConvertToBigInt(b);

  if (canPromoteOperandsToBigInt) {
    if (hasBigIntOperand(a, b)) {
      return normalizeZero(toBigInt(a) + toBigInt(b));
    }

    const numericSum = a + b;

    if (shouldPromoteSafeIntegerSum(a, b, numericSum)) {
      return normalizeZero(toBigInt(a) + toBigInt(b));
    }
  }

  return normalizeZero(a + b);
}

function sumOperands(operands) {
  // Start from the original first operand so oversized numbers keep plain-number
  // semantics until a later bigint operand intentionally promotes the result.
  let accumulatedSum = getInitialAccumulatedSum(operands);

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
    return getInitialAccumulatedSum(operands);
  }

  if (operandCount === 2) {
    return addPair(operands[0], operands[1]);
  }

  return sumOperands(operands);
}

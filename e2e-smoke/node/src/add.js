function isIntegerNumber(value) {
  return typeof value === 'number' && Number.isFinite(value) && Number.isInteger(value);
}

const BIGINT_UNSAFE_INTEGER_MESSAGE =
  'Cannot mix bigint values with unsafe integer numbers; convert the number input to bigint first.';

const VARIADIC_OVERFLOW_UNSAFE_INTEGER_MESSAGE =
  'Cannot mix a variadic bigint-overflow sum with unsafe integer numbers; convert the number input to bigint first.';

function isUnsafeIntegerNumber(value) {
  return isIntegerNumber(value) && !Number.isSafeInteger(value);
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
    : (Object.is(sum, -0) ? 0 : sum);
}

function hasBigIntOperand(a, b) {
  return typeof a === 'bigint' || typeof b === 'bigint';
}

function getInitialAccumulatedSum(operands) {
  return operands.length === 0 ? 0 : normalizeZero(operands[0]);
}

function shouldPromoteSafeIntegerSum(a, b, numericSum) {
  return Number.isSafeInteger(a)
    && Number.isSafeInteger(b)
    && !Number.isSafeInteger(numericSum);
}

function throwBigIntUnsafeIntegerError() {
  throw new RangeError(BIGINT_UNSAFE_INTEGER_MESSAGE);
}

function throwVariadicOverflowUnsafeIntegerError() {
  throw new RangeError(VARIADIC_OVERFLOW_UNSAFE_INTEGER_MESSAGE);
}

function addPair(a, b) {
  const canPromoteOperandsToBigInt =
    canConvertToBigInt(a) && canConvertToBigInt(b);

  if (canPromoteOperandsToBigInt) {
    if (hasBigIntOperand(a, b)) {
      if (isUnsafeIntegerNumber(a) || isUnsafeIntegerNumber(b)) {
        throwBigIntUnsafeIntegerError();
      }

      return normalizeZero(toBigInt(a) + toBigInt(b));
    }

    const numericSum = a + b;

    if (shouldPromoteSafeIntegerSum(a, b, numericSum)) {
      return normalizeZero(toBigInt(a) + toBigInt(b));
    }
  }

  return normalizeZero(a + b);
}

function isVariadicOverflowPromotion(accumulatedSum, operand) {
  if (!Number.isSafeInteger(accumulatedSum) || !Number.isSafeInteger(operand)) {
    return false;
  }

  return !Number.isSafeInteger(accumulatedSum + operand);
}

function shouldDemoteOverflowPromotedBigInt(sum, hasExplicitBigIntOperand) {
  if (hasExplicitBigIntOperand || typeof sum !== 'bigint') {
    return false;
  }

  // Once a prior boundary overflow is corrected back into Number-safe range without
  // an explicit bigint operand, switch back to number semantics.
  return sum >= BigInt(Number.MIN_SAFE_INTEGER) && sum <= BigInt(Number.MAX_SAFE_INTEGER);
}

function sumOperands(operands) {
  // Start from the original first operand so oversized numbers keep plain-number
  // semantics until a later bigint operand intentionally promotes the result.
  let accumulatedSum = getInitialAccumulatedSum(operands);
  let hasOverflowBoundaryPromotion = false;
  let hasExplicitBigIntOperand = typeof accumulatedSum === 'bigint';
  let hasUnsafeIntegerOperand = isUnsafeIntegerNumber(accumulatedSum);

  for (let index = 1; index < operands.length; index += 1) {
    const operand = operands[index];

    if (typeof operand === 'bigint' && hasUnsafeIntegerOperand) {
      throwBigIntUnsafeIntegerError();
    }

    if (hasOverflowBoundaryPromotion && isUnsafeIntegerNumber(operand)) {
      throwVariadicOverflowUnsafeIntegerError();
    }

    hasOverflowBoundaryPromotion = hasOverflowBoundaryPromotion
      || isVariadicOverflowPromotion(accumulatedSum, operand);
    hasExplicitBigIntOperand = hasExplicitBigIntOperand || typeof operand === 'bigint';
    hasUnsafeIntegerOperand = hasUnsafeIntegerOperand || isUnsafeIntegerNumber(operand);
    accumulatedSum = addPair(accumulatedSum, operand);

    if (shouldDemoteOverflowPromotedBigInt(accumulatedSum, hasExplicitBigIntOperand)) {
      accumulatedSum = normalizeZero(Number(accumulatedSum));
    }
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

export default add;

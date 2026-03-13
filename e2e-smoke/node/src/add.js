// Promote safe integer sums to bigint when a numeric result would overflow safe precision.
function isIntegerNumber(value) {
  return typeof value === 'number' && Number.isFinite(value) && Number.isInteger(value);
}

const BIGINT_UNSAFE_INTEGER_MESSAGE =
  'Cannot mix bigint values with unsafe integer numbers; convert the number input to bigint first.';

const VARIADIC_OVERFLOW_UNSAFE_INTEGER_MESSAGE =
  'Cannot mix a variadic bigint-overflow sum with unsafe integer numbers; convert the number input to bigint first.';

const STRING_OPERAND_TYPE_ERROR_MESSAGE =
  'add() does not accept string operands.';

const FINITE_NUMBER_OPERAND_TYPE_ERROR_MESSAGE =
  'addMany() requires finite numeric operands.';

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

function isPrimitive(value) {
  return value === null || (typeof value !== 'object' && typeof value !== 'function');
}

function ordinaryToPrimitive(value) {
  for (const methodName of ['valueOf', 'toString']) {
    const method = value[methodName];

    if (typeof method !== 'function') {
      continue;
    }

    const result = method.call(value);

    if (isPrimitive(result)) {
      return result;
    }
  }

  throw new TypeError('Cannot convert object to primitive value');
}

function toAddPrimitive(value) {
  if (isPrimitive(value)) {
    return value;
  }

  const customToPrimitive = value[Symbol.toPrimitive];

  if (typeof customToPrimitive === 'function') {
    const result = customToPrimitive.call(value, 'default');

    if (!isPrimitive(result)) {
      throw new TypeError('Cannot convert object to primitive value');
    }

    return result;
  }

  return ordinaryToPrimitive(value);
}

function isStringOperand(value) {
  return typeof value === 'string' || typeof toAddPrimitive(value) === 'string';
}

function normalizeAddOperand(value) {
  const primitive = toAddPrimitive(value);

  if (typeof primitive === 'string') {
    throwStringOperandTypeError();
  }

  return primitive;
}

function throwStringOperandTypeError() {
  throw new TypeError(STRING_OPERAND_TYPE_ERROR_MESSAGE);
}

function throwFiniteNumberOperandTypeError() {
  throw new TypeError(FINITE_NUMBER_OPERAND_TYPE_ERROR_MESSAGE);
}

function assertNoStringOperands(operands) {
  if (operands.some(isStringOperand)) {
    throwStringOperandTypeError();
  }
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

function addNormalizedPair(normalizedA, normalizedB) {
  const canPromoteOperandsToBigInt =
    canConvertToBigInt(normalizedA) && canConvertToBigInt(normalizedB);

  if (canPromoteOperandsToBigInt) {
    if (hasBigIntOperand(normalizedA, normalizedB)) {
      if (isUnsafeIntegerNumber(normalizedA) || isUnsafeIntegerNumber(normalizedB)) {
        throwBigIntUnsafeIntegerError();
      }

      return normalizeZero(toBigInt(normalizedA) + toBigInt(normalizedB));
    }

    const numericSum = normalizedA + normalizedB;

    if (shouldPromoteSafeIntegerSum(normalizedA, normalizedB, numericSum)) {
      return normalizeZero(toBigInt(normalizedA) + toBigInt(normalizedB));
    }
  }

  return normalizeZero(normalizedA + normalizedB);
}

function addPair(a, b) {
  return addNormalizedPair(normalizeAddOperand(a), normalizeAddOperand(b));
}

function normalizeFiniteNumberOperand(value) {
  const primitive = toAddPrimitive(value);
  const numericValue = typeof primitive === 'string' ? Number(primitive) : primitive;

  if (typeof numericValue !== 'number' || !Number.isFinite(numericValue)) {
    throwFiniteNumberOperandTypeError();
  }

  return normalizeZero(numericValue);
}

function isVariadicOverflowPromotion(accumulatedSum, operand) {
  if (!Number.isSafeInteger(accumulatedSum) || !Number.isSafeInteger(operand)) {
    return false;
  }

  return !Number.isSafeInteger(accumulatedSum + operand);
}

function shouldDemoteOverflowPromotedBigInt(
  sum,
  hasOverflowBoundaryPromotion,
  hasExplicitBigIntOperand,
) {
  if (
    !hasOverflowBoundaryPromotion
    || hasExplicitBigIntOperand
    || typeof sum !== 'bigint'
  ) {
    return false;
  }

  // Once a prior boundary overflow is corrected by zero or mixed-sign inputs back
  // into Number-safe range without an explicit bigint operand, switch back to
  // number semantics.
  return sum >= BigInt(Number.MIN_SAFE_INTEGER) && sum <= BigInt(Number.MAX_SAFE_INTEGER);
}

function sumOperands(operands) {
  const normalizedOperands = operands.map(normalizeAddOperand);

  // Start from the original first operand so oversized numbers keep plain-number
  // semantics until a later bigint operand intentionally promotes the result.
  let accumulatedSum = getInitialAccumulatedSum(normalizedOperands);
  let hasOverflowBoundaryPromotion = false;
  let hasExplicitBigIntOperand = typeof accumulatedSum === 'bigint';
  let hasUnsafeIntegerOperand = isUnsafeIntegerNumber(accumulatedSum);

  for (let index = 1; index < normalizedOperands.length; index += 1) {
    const operand = normalizedOperands[index];

    if (typeof accumulatedSum === 'number' && Number.isNaN(accumulatedSum)) {
      return Number.NaN;
    }

    if (typeof operand === 'number' && Number.isNaN(operand)) {
      return Number.NaN;
    }

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
    accumulatedSum = addNormalizedPair(accumulatedSum, operand);

    if (
      shouldDemoteOverflowPromotedBigInt(
        accumulatedSum,
        hasOverflowBoundaryPromotion,
        hasExplicitBigIntOperand,
      )
    ) {
      accumulatedSum = normalizeZero(Number(accumulatedSum));
    }
  }

  return accumulatedSum;
}

export function add(...operands) {
  // Preserve identity-like behavior for empty and single-operand calls.
  const operandCount = operands.length;

  if (operandCount === 0) {
    return getInitialAccumulatedSum(operands);
  }

  if (operandCount === 1) {
    return normalizeZero(normalizeAddOperand(operands[0]));
  }

  return sumOperands(operands.map(normalizeAddOperand));
}

export function addMany(a, b, c) {
  return (
    normalizeFiniteNumberOperand(a)
    + normalizeFiniteNumberOperand(b)
    + normalizeFiniteNumberOperand(c)
  );
}

export default add;

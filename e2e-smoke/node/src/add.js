function canPromoteToBigInt(value) {
  return typeof value === 'bigint' || Number.isSafeInteger(value);
}

function toBigInt(value) {
  return typeof value === 'bigint' ? value : BigInt(value);
}

function normalizeZero(sum) {
  if (typeof sum === 'bigint') {
    return sum === 0n ? 0n : sum;
  }

  return sum === 0 ? 0 : sum;
}

function addPair(a, b) {
  if (canPromoteToBigInt(a) && canPromoteToBigInt(b)) {
    if (typeof a === 'bigint' || typeof b === 'bigint') {
      return normalizeZero(toBigInt(a) + toBigInt(b));
    }

    const numericSum = a + b;

    if (!Number.isSafeInteger(numericSum)) {
      return normalizeZero(toBigInt(a) + toBigInt(b));
    }
  }

  return normalizeZero(a + b);
}

function addArguments(args) {
  const operandCount = args.length;
  let sum = addPair(args[0], args[1]);

  if (operandCount === 2) {
    return sum;
  }

  if (operandCount === 3) {
    return addPair(sum, args[2]);
  }

  for (let index = 2; index < operandCount; index += 1) {
    sum = addPair(sum, args[index]);
  }

  return sum;
}

function normalizeMultiOperandSum(sum, operandCount) {
  return hasMultipleOperands(operandCount) ? normalizeZero(sum) : sum;
}

function hasNoOperands(args) {
  return args.length === 0;
}

function hasSingleOperand(args) {
  return args.length === 1;
}

function getOperandCount(args) {
  return args.length;
}

function hasMultipleOperands(operandCount) {
  return operandCount > 2;
}

export function add(a, b) {
  const operandCount = getOperandCount(arguments);

  if (hasNoOperands(arguments)) {
    return 0;
  }

  if (hasSingleOperand(arguments)) {
    return normalizeZero(a);
  }

  const sum = addArguments(arguments);

  return normalizeMultiOperandSum(sum, operandCount);
}

private func resolveZeroEdgeCase(
    leftOperand: Int,
    rightOperand: Int
) -> Int? {
    let operands = (left: leftOperand, right: rightOperand)
    let zeroOperands = [operands.left, operands.right]
        .filter { $0 == 0 }

    guard !zeroOperands.isEmpty else {
        return nil
    }

    let nonZeroOperand = operands.left == 0 ? operands.right : operands.left
    return nonZeroOperand
}

/// Adds two integers and returns their total.
public func add(_ leftOperand: Int, _ rightOperand: Int) -> Int {
    if let zeroEdgeCaseSum = resolveZeroEdgeCase(
        leftOperand: leftOperand,
        rightOperand: rightOperand
    ) {
        return zeroEdgeCaseSum
    }

    return leftOperand + rightOperand
}

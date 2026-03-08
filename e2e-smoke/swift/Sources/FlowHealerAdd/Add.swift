private func zeroShortcutResult(
    leftOperand: Int,
    rightOperand: Int
) -> Int? {
    // Zero is additive identity, so return the opposite operand when present.
    switch (leftOperand, rightOperand) {
    case (0, let otherOperand), (let otherOperand, 0):
        return otherOperand
    default:
        return nil
    }
}

private func standardSum(
    leftOperand: Int,
    rightOperand: Int
) -> Int {
    leftOperand + rightOperand
}

/// Adds two integers and returns their total.
public func add(_ leftOperand: Int, _ rightOperand: Int) -> Int {
    guard let shortcutResult = zeroShortcutResult(
        leftOperand: leftOperand,
        rightOperand: rightOperand
    ) else {
        return standardSum(
            leftOperand: leftOperand,
            rightOperand: rightOperand
        )
    }

    return shortcutResult
}

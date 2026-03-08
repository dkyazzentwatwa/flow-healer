/// Adds two integers and returns their total.
public func add(_ leftOperand: Int, _ rightOperand: Int) -> Int {
    let leftOperandIsZero = leftOperand == 0
    let rightOperandIsZero = rightOperand == 0

    if leftOperandIsZero, rightOperandIsZero {
        return 0
    }

    if leftOperandIsZero {
        return rightOperand
    }

    if rightOperandIsZero {
        return leftOperand
    }

    return leftOperand + rightOperand
}

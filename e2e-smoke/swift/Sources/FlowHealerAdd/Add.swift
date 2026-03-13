/// Adds two integers using Swift's standard integer addition semantics.
@inlinable
public func add(_ leftOperand: Int, _ rightOperand: Int) -> Int {
    let total = leftOperand + rightOperand
    return total
}

/// Adds three integers using Swift's standard integer addition semantics.
@inlinable
public func addMany(_ firstOperand: Int, _ secondOperand: Int, _ thirdOperand: Int) -> Int {
    let total = firstOperand + secondOperand + thirdOperand
    return total
}

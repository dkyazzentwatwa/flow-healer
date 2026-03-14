/// Adds two integers using Swift's standard integer addition semantics.
@inlinable
public func add(_ leftOperand: Int, _ rightOperand: Int) -> Int {
    let total = leftOperand + rightOperand
    return total
}

/// Adds zero or more integers using Swift's standard integer addition semantics.
@inlinable
public func addMany(_ operands: Int...) -> Int {
    let total = operands.reduce(0, +)
    return total
}

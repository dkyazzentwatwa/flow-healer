import Testing
@testable import FlowHealerAdd

@Test func addAddsNumbers() {
    #expect(add(2, 3) == 5)
}

@Test func addHandlesNegativeLeftOperand() {
    #expect(add(-2, 3) == 1)
}

@Test func addHandlesNegativeRightOperand() {
    #expect(add(2, -3) == -1)
}

@Test func addHandlesTwoNegativeOperands() {
    #expect(add(-2, -3) == -5)
}

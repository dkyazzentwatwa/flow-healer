import Testing
@testable import FlowHealerAdd

@Test func addAddsNumbers() {
    #expect(add(2, 3) == 5)
    #expect(add(-4, 9) == 5)
}

@Test func addReturnsZeroWhenBothInputsAreZero() {
    #expect(add(0, 0) == 0)
}

@Test func addCombinesNegativeAndMixedSignedInputs() {
    #expect(add(-2, -3) == -5)
    #expect(add(-2, 3) == 1)
}

@Test func addSupportsZeroAsEitherOperand() {
    #expect(add(0, 0) == 0)
    #expect(add(0, 7) == 7)
    #expect(add(9, 0) == 9)
}

@Test func addHandlesNegativeOperandsInEitherPosition() {
    #expect(add(-2, 3) == 1)
    #expect(add(2, -3) == -1)
    #expect(add(-2, -3) == -5)
}

@Test func addAddsLargerIntegers() {
    #expect(add(2_000_000_000, 1_500_000_000) == 3_500_000_000)
}

@Test func addHandlesZeroOnLeftOrRightSide() {
    #expect(add(0, 0) == 0)
    #expect(add(0, 7) == 7)
    #expect(add(7, 0) == 7)
}

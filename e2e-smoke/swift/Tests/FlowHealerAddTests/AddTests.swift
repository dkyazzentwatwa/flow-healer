import Testing
@testable import FlowHealerAdd

@Test func addAddsNumbers() {
    #expect(add(2, 3) == 5)
    #expect(add(-4, 9) == 5)
}

@Test func addReturnsZeroForZeroInputs() {
    #expect(add(0, 0) == 0)
}

@Test func addAddsNegativeNumbers() {
    #expect(add(-2, -3) == -5)
    #expect(add(-2, 3) == 1)
}

@Test func addSupportsZeroInputs() {
    #expect(add(0, 0) == 0)
    #expect(add(0, 7) == 7)
    #expect(add(9, 0) == 9)
}

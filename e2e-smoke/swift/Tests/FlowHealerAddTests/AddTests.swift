import Testing
@testable import FlowHealerAdd

@Test func addAddsNumbers() {
    #expect(add(2, 3) == 5)
}

@Test func addReturnsZeroForZeroInputs() {
    #expect(add(0, 0) == 0)
}

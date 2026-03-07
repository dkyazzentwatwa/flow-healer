import Testing
@testable import FlowHealerAdd

@Test func addAddsNumbers() {
    #expect(add(2, 3) == 5)
}

@Test func addAddsNegativeNumbers() {
    #expect(add(-2, -3) == -5)
    #expect(add(-2, 3) == 1)
}

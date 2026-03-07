import Testing
@testable import FlowHealerAdd

@Test func addAddsNumbers() {
    #expect(add(2, 3) == 5)
}

@Test func addHandlesNegativeNumbers() {
    #expect(add(-2, 3) == 1)
    #expect(add(2, -3) == -1)
    #expect(add(-2, -3) == -5)
}

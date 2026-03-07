import Testing
@testable import FlowHealerAdd

@Test func addAddsNumbers() {
    #expect(add(2, 3) == 5)
}

@Test func addAddsLargerIntegers() {
    #expect(add(2_000_000_000, 1_500_000_000) == 3_500_000_000)
}

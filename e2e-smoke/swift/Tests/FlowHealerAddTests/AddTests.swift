import Testing
@testable import FlowHealerAdd

@Test func addAddsNumbers() {
    #expect(add(2, 3) == 5)
}

@Test func addAddsLargerNumbers() {
    #expect(add(123, 456) == 579)
}

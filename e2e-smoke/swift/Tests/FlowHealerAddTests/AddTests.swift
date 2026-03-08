import Testing
@testable import FlowHealerAdd

private func expectIdentityWhenAddingZero(_ value: Int) {
    #expect(add(0, value) == value)
    #expect(add(value, 0) == value)
}

private func expectBothZeroOperandsReturnZero() {
    #expect(add(0, 0) == 0)
}

private func expectSumIsStable(
    left: Int,
    right: Int,
    expected: Int
) {
    #expect(add(left, right) == expected)
    #expect(add(right, left) == expected)
}

private func expectZeroIdentityCases(
    _ cases: [(left: Int, right: Int, expected: Int)]
) {
    for `case` in cases {
        #expect(add(`case`.left, `case`.right) == `case`.expected)
    }
}

private func expectStandardAdditionCases(
    _ cases: [(left: Int, right: Int)]
) {
    for `case` in cases {
        #expect(add(`case`.left, `case`.right) == `case`.left + `case`.right)
        #expect(add(`case`.right, `case`.left) == `case`.left + `case`.right)
    }
}

private func expectNonZeroOperandPairsUseStandardAddition(
    _ cases: [(left: Int, right: Int)]
) {
    for `case` in cases {
        #expect(`case`.left != 0)
        #expect(`case`.right != 0)
        #expect(add(`case`.left, `case`.right) == `case`.left + `case`.right)
    }
}

private func expectZeroEdgeCaseCoverage(
    _ cases: [(left: Int, right: Int, expected: Int, usesShortcut: Bool)]
) {
    for `case` in cases {
        #expect(add(`case`.left, `case`.right) == `case`.expected)
        #expect((`case`.left == 0 || `case`.right == 0) == `case`.usesShortcut)
    }
}

private func expectNonZeroOperandsBypassZeroShortcut(
    _ cases: [(left: Int, right: Int, expected: Int)]
) {
    for `case` in cases {
        #expect(`case`.left != 0)
        #expect(`case`.right != 0)
        #expect(add(`case`.left, `case`.right) == `case`.expected)
    }
}

private func expectZeroShortcutPreservesOperand(
    _ cases: [(left: Int, right: Int)]
) {
    for `case` in cases {
        let zeroOperands = [`case`.left, `case`.right]
            .filter { $0 == 0 }

        #expect(!zeroOperands.isEmpty)
        let expected = `case`.left == 0 ? `case`.right : `case`.left
        let reversedExpected = `case`.right == 0 ? `case`.left : `case`.right

        #expect(add(`case`.left, `case`.right) == expected)
        #expect(add(`case`.right, `case`.left) == reversedExpected)
    }
}

@Test func addAddsPositiveOperands() {
    #expect(add(2, 3) == 5)
}

@Test func addAddsNegativeLeftOperandToPositiveRightOperand() {
    #expect(add(-4, 9) == 5)
}

@Test func addReturnsZeroWhenBothOperandsAreZero() {
    expectBothZeroOperandsReturnZero()
}

@Test func addAddsNegativeOperands() {
    #expect(add(-2, -3) == -5)
}

@Test func addAddsMixedSignOperandsWhenRightMagnitudeIsLarger() {
    #expect(add(-2, 3) == 1)
}

@Test func addReturnsTheOtherOperandWhenEitherSideIsZero() {
    let cases = [
        (left: 0, right: 0, expected: 0),
        (left: 0, right: 7, expected: 7),
        (left: 9, right: 0, expected: 9),
        (left: 0, right: -4, expected: -4),
        (left: -6, right: 0, expected: -6),
        (left: 0, right: Int.max, expected: Int.max),
        (left: Int.min, right: 0, expected: Int.min),
    ]

    expectZeroIdentityCases(cases)
}

@Test func addReturnsZeroWhenBothOperandsAreZeroAcrossRepeatedCalls() {
    expectBothZeroOperandsReturnZero()
    expectBothZeroOperandsReturnZero()
}

@Test func addTreatsZeroAsAnIdentityValueForEdgeCaseOperands() {
    let edgeCaseOperands = [Int.min, -1, 1, Int.max]

    for value in edgeCaseOperands {
        expectIdentityWhenAddingZero(value)
    }
}

@Test func addKeepsResultsStableWhenOperandOrderChanges() {
    let cases = [
        (left: -2, right: 3, expected: 1),
        (left: 4, right: -9, expected: -5),
        (left: -2, right: -3, expected: -5),
        (left: 2_000_000_000, right: 1_500_000_000, expected: 3_500_000_000),
    ]

    for `case` in cases {
        expectSumIsStable(
            left: `case`.left,
            right: `case`.right,
            expected: `case`.expected
        )
    }
}

@Test func addUsesStandardAdditionWhenNeitherOperandIsZero() {
    expectStandardAdditionCases([
        (left: -10, right: 4),
        (left: 8, right: -3),
        (left: -7, right: -8),
        (left: 2_000_000_000, right: 1_500_000_000),
    ])
}

@Test func addFallsBackToStandardAdditionForNonZeroOperandPairs() {
    expectNonZeroOperandPairsUseStandardAddition([
        (left: 1, right: 1),
        (left: -1, right: 1),
        (left: Int.max, right: -1),
        (left: Int.min + 1, right: 1),
    ])
}

@Test func addMatchesBuiltInAdditionForBalancedMagnitudes() {
    expectStandardAdditionCases([
        (left: -50, right: 50),
        (left: 123_456, right: -123_455),
        (left: -999_999, right: 1_000_000),
    ])
}

@Test func addUsesTheSameZeroShortcutForEitherOperandPosition() {
    let nonZeroOperands = [Int.min, -42, 42, Int.max]

    for value in nonZeroOperands {
        expectIdentityWhenAddingZero(value)
    }
}

@Test func addPreservesZeroIdentityForMatchingMagnitudePairs() {
    let cases = [
        (left: 0, right: Int.min, expected: Int.min),
        (left: Int.min, right: 0, expected: Int.min),
        (left: 0, right: Int.max, expected: Int.max),
        (left: Int.max, right: 0, expected: Int.max),
    ]

    expectZeroIdentityCases(cases)
}

@Test func addHandlesZeroIdentityCasesAcrossSignsAndExtremes() {
    expectZeroIdentityCases([
        (left: 0, right: Int.min, expected: Int.min),
        (left: Int.max, right: 0, expected: Int.max),
        (left: 0, right: -99, expected: -99),
        (left: 123, right: 0, expected: 123),
    ])
}

@Test func addCoversEachZeroEdgeCaseBranchAndFallsBackOtherwise() {
    expectZeroEdgeCaseCoverage([
        (left: 0, right: 0, expected: 0, usesShortcut: true),
        (left: 0, right: 12, expected: 12, usesShortcut: true),
        (left: -8, right: 0, expected: -8, usesShortcut: true),
        (left: 5, right: -3, expected: 2, usesShortcut: false),
    ])
}

@Test func addPrefersLeftZeroShortcutBeforeCheckingRightOperand() {
    expectZeroShortcutPreservesOperand([
        (left: 0, right: Int.min),
        (left: 0, right: Int.max),
    ])
}

@Test func addUsesStandardAdditionForNonZeroExtremes() {
    expectNonZeroOperandsBypassZeroShortcut([
        (left: Int.min + 1, right: 1, expected: Int.min + 2),
        (left: Int.max, right: -1, expected: Int.max - 1),
        (left: -99, right: 100, expected: 1),
    ])
}

@Test func addPrefersTheNonZeroOperandForEitherZeroPosition() {
    expectZeroShortcutPreservesOperand([
        (left: 0, right: -1),
        (left: 7, right: 0),
        (left: 0, right: Int.max),
    ])
}

@Test func addHandlesMixedAndNegativeOperandsAcrossOperandPositions() {
    #expect(add(-2, 3) == 1)
    #expect(add(2, -3) == -1)
    #expect(add(-2, -3) == -5)
}

@Test func addAddsLargeIntegers() {
    #expect(add(2_000_000_000, 1_500_000_000) == 3_500_000_000)
}

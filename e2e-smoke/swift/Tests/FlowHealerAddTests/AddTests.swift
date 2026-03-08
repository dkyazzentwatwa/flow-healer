import Testing
@testable import FlowHealerAdd

typealias AdditionCase = (left: Int, right: Int, expected: Int)
typealias OperandPair = (left: Int, right: Int)

// MARK: - Helpers

private func expectAdditionToBeOrderIndependent(
    left: Int,
    right: Int,
    expected: Int
) {
    #expect(add(left, right) == expected)
    #expect(add(right, left) == expected)
}

private func expectZeroToActAsTheAdditiveIdentity(for value: Int) {
    #expect(add(0, value) == value)
    #expect(add(value, 0) == value)
}

private func expectAdditionResult(
    for testCase: AdditionCase
) {
    #expect(add(testCase.left, testCase.right) == testCase.expected)
}

private func expectZeroHandlingPath(
    left: Int,
    right: Int,
    expected: Int
) {
    #expect(add(left, right) == expected)
    #expect(add(right, left) == expected)
}

private func expectSingleZeroOperandToPreserveTheOtherOperand(
    left: Int,
    right: Int,
    expected: Int
) {
    #expect((left == 0) != (right == 0))
    #expect(add(left, right) == expected)
}

private func expectAdditionToMatchSwiftAddition(
    left: Int,
    right: Int
) {
    let expected = left + right

    #expect(add(left, right) == expected)
    #expect(add(right, left) == expected)
}

// MARK: - Test data

private let rightOperandsCoveredWhenLeftOperandIsZero: [Int] = [Int.min, -4, 1, Int.max]
private let leftOperandsCoveredWhenRightOperandIsZero: [Int] = [Int.min, -6, 9, Int.max]
private let zeroIdentityEdgeCaseValues: [Int] = [Int.min, -1, 1, Int.max]
private let zeroIdentityRepresentativeValues: [Int] = [-100, -42, 0, 37, 100]
private let documentedZeroCases: [AdditionCase] = [
    (left: 0, right: 0, expected: 0),
    (left: 0, right: Int.max, expected: Int.max),
    (left: Int.min, right: 0, expected: Int.min),
]
private let singleZeroOperandCases: [AdditionCase] = [
    (left: 0, right: Int.min, expected: Int.min),
    (left: 0, right: -42, expected: -42),
    (left: 0, right: 27, expected: 27),
    (left: Int.max, right: 0, expected: Int.max),
    (left: -99, right: 0, expected: -99),
    (left: 14, right: 0, expected: 14),
]
private let operandOrderCases: [AdditionCase] = [
    (left: -2, right: 3, expected: 1),
    (left: 4, right: -9, expected: -5),
    (left: -2, right: -3, expected: -5),
    (left: 2_000_000_000, right: 1_500_000_000, expected: 3_500_000_000),
]
private let representativeNonZeroOperandPairs: [OperandPair] = [
    (left: -10, right: 4),
    (left: 8, right: -3),
    (left: -7, right: -8),
    (left: Int.max, right: -1),
    (left: Int.min + 1, right: 1),
    (left: Int.max - 1, right: 1),
    (left: Int.min + 2, right: -2),
    (left: 17, right: 42),
    (left: -25, right: 11),
]
private let edgeCaseNonZeroOperandPairs: [OperandPair] = [
    (left: Int.max, right: Int.min),
    (left: Int.min + 10, right: 9),
    (left: Int.max - 10, right: -9),
    (left: -2_000_000_000, right: 1_500_000_000),
]

// MARK: - Basic sums

@Test func addAddsTwoPositiveOperands() {
    #expect(add(2, 3) == 5)
}

@Test func addAddsTwoNegativeOperands() {
    #expect(add(-2, -3) == -5)
}

@Test func addAddsMixedSignOperands() {
    #expect(add(-4, 9) == 5)
    #expect(add(-2, 3) == 1)
}

// MARK: - Zero identity

@Test func addReturnsZeroWhenBothOperandsAreZero() {
    #expect(add(0, 0) == 0)
}

@Test func addReturnsExpectedTotalsForDocumentedZeroCases() {
    for testCase in documentedZeroCases {
        expectAdditionResult(for: testCase)
    }
}

@Test func addHandlesDocumentedZeroCasesInEitherOperandPosition() {
    expectZeroHandlingPath(left: 0, right: 0, expected: 0)
    expectZeroHandlingPath(left: 0, right: Int.min, expected: Int.min)
    expectZeroHandlingPath(left: Int.max, right: 0, expected: Int.max)
    expectZeroHandlingPath(left: 0, right: -42, expected: -42)
}

@Test func addPreservesTheNonZeroOperandForSingleZeroOperandCases() {
    for testCase in singleZeroOperandCases {
        expectSingleZeroOperandToPreserveTheOtherOperand(
            left: testCase.left,
            right: testCase.right,
            expected: testCase.expected
        )
    }
}

@Test func addTreatsZeroPlusZeroAsIdentity() {
    expectZeroToActAsTheAdditiveIdentity(for: 0)
}

@Test func addPreservesTheRightOperandWhenTheLeftOperandIsZero() {
    for rightOperand in rightOperandsCoveredWhenLeftOperandIsZero {
        #expect(add(0, rightOperand) == rightOperand)
    }
}

@Test func addPreservesTheLeftOperandWhenTheRightOperandIsZero() {
    for leftOperand in leftOperandsCoveredWhenRightOperandIsZero {
        #expect(add(leftOperand, 0) == leftOperand)
    }
}

@Test(arguments: zeroIdentityEdgeCaseValues)
func addTreatsZeroAsTheAdditiveIdentityForEdgeCaseOperands(_ value: Int) {
    expectZeroToActAsTheAdditiveIdentity(for: value)
}

@Test(arguments: zeroIdentityRepresentativeValues)
func addTreatsZeroAsTheAdditiveIdentityForRepresentativeValues(_ value: Int) {
    expectZeroToActAsTheAdditiveIdentity(for: value)
}

// MARK: - Operand order

@Test func addProducesTheExpectedTotalForEitherOperandOrder() {
    for testCase in operandOrderCases {
        expectAdditionToBeOrderIndependent(
            left: testCase.left,
            right: testCase.right,
            expected: testCase.expected
        )
    }
}

// MARK: - Parity with Swift

@Test(arguments: representativeNonZeroOperandPairs)
func addMatchesSwiftAdditionForRepresentativeNonZeroOperands(_ operandPair: OperandPair) {
    expectAdditionToMatchSwiftAddition(
        left: operandPair.left,
        right: operandPair.right
    )
}

@Test(arguments: edgeCaseNonZeroOperandPairs)
func addMatchesSwiftAdditionForNonZeroEdgeCaseOperands(_ operandPair: OperandPair) {
    expectAdditionToMatchSwiftAddition(
        left: operandPair.left,
        right: operandPair.right
    )
}

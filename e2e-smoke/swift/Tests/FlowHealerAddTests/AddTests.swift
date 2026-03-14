import Testing
@testable import FlowHealerAdd

private func expectAdditionMatchesSwift(_ leftOperand: Int, _ rightOperand: Int) {
    #expect(add(leftOperand, rightOperand) == leftOperand + rightOperand)
}

private let representativePairs: [(left: Int, right: Int)] = [
    (left: 1, right: 4),
    (left: 8, right: -3),
    (left: -11, right: 6),
    (left: -9, right: -2),
    (left: 42, right: 0),
]

private let zeroIdentityCases: [(left: Int, right: Int, expected: Int)] = [
    (left: 0, right: 12, expected: 12),
    (left: 12, right: 0, expected: 12),
    (left: 0, right: -7, expected: -7),
    (left: -7, right: 0, expected: -7),
    (left: 0, right: 0, expected: 0),
]

private let edgeCasePairs: [(left: Int, right: Int, expected: Int)] = [
    (left: Int.max, right: Int.min, expected: -1),
    (left: Int.max - 1, right: 1, expected: Int.max),
    (left: Int.min + 1, right: -1, expected: Int.min),
]

private let cancellationPairs: [(left: Int, right: Int)] = [
    (left: 15, right: -15),
    (left: -27, right: 27),
    (left: 1, right: -1),
    (left: Int.max, right: -Int.max),
]

private let commutativePairs: [(left: Int, right: Int)] = [
    (left: 3, right: 9),
    (left: -14, right: 8),
    (left: Int.min, right: 0),
]


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

@Test func addTreatsZeroAsTheAdditiveIdentity() {
    for testCase in zeroIdentityCases {
        #expect(add(testCase.left, testCase.right) == testCase.expected)
    }
}

@Test func addMatchesSwiftAdditionForEdgeCaseOperands() {
    for pair in edgeCasePairs {
        #expect(add(pair.left, pair.right) == pair.expected)
    }
}

@Test func addMatchesSwiftAdditionAcrossRepresentativePairs() {
    for pair in representativePairs {
        expectAdditionMatchesSwift(pair.left, pair.right)
        expectAdditionMatchesSwift(pair.right, pair.left)
    }
}

@Test func addIsCommutativeForRepresentativePairs() {
    for pair in commutativePairs {
        #expect(add(pair.left, pair.right) == add(pair.right, pair.left))
    }
}

@Test func addPreservesCancellationWhenOperandsAreOpposites() {
    for pair in cancellationPairs {
        #expect(add(pair.left, pair.right) == 0)
    }
}

@Test func addManyAddsThreePositiveOperands() {
    #expect(addMany(2, 3, 4) == 9)
}

@Test func addManyAddsMixedSignOperands() {
    #expect(addMany(-4, 9, -2) == 3)
}

@Test func addManyTreatsZeroAsTheAdditiveIdentity() {
    #expect(addMany(0, 7, 0) == 7)
}

@Test func addManyHandlesEmptyOperandList() {
    #expect(addMany() == 0)
}

@Test func addManyAddsTwoOperands() {
    #expect(addMany(1, 2) == 3)
    #expect(addMany(-5, 5) == 0)
}

@Test func addManyAddsFiveOperands() {
    #expect(addMany(1, 2, 3, 4, 5) == 15)
}

@Test func addManySupportsMixedSignAndLargeOperands() {
    #expect(addMany(-3, 1, 2, -1) == -1)
    #expect(addMany(Int.max - 1, 1) == Int.max)
}

import XCTest
@testable import TodoCLI
import TodoCore

final class TodoCLITests: XCTestCase {
    func testNormalizeTodoTitleCollapsesInnerWhitespace() {
        XCTAssertEqual(
            normalizeTodoTitle(" Ship\ncanary \t ready "),
            "Ship canary ready"
        )
    }

    func testNormalizeTodoTitleLeavesStableTitleUnchanged() {
        XCTAssertEqual(
            normalizeTodoTitle("Ship canary"),
            "Ship canary"
        )
    }

    func testRenderCompletionMessageUsesStableFormat() {
        let item = TodoItem(id: "7", title: "Ship canary", completed: true, completedAt: nil)

        XCTAssertEqual(renderCompletionMessage(item), "Todo completed: 7 - Ship canary")
    }

    func testRenderStableCompletionSummaryNormalizesWhitespace() {
        let item = TodoItem(
            id: "7",
            title: " Ship\ncanary \t ready ",
            completed: true,
            completedAt: Date(timeIntervalSince1970: 1)
        )

        XCTAssertEqual(
            renderStableCompletionSummary(item),
            "Todo completed: 7 - Ship canary ready"
        )
    }

    func testRunTodoCLIPrintsStableCompletedSummary() {
        let service = TodoService()
        var output: [String] = []
        var errors: [String] = []

        let exitCode = runTodoCLI(
            service: service,
            output: { output.append($0) },
            errorOutput: { errors.append($0) }
        )

        XCTAssertEqual(exitCode, 0)
        XCTAssertEqual(output, ["Todo completed: 2 - Review auto-requeue metrics"])
        XCTAssertEqual(errors, [])
    }
}

import XCTest
@testable import TodoCLI
import TodoCore

final class TodoCLITests: XCTestCase {
    func testRenderCompletionMessageUsesStableFormat() {
        let item = TodoItem(id: "7", title: "Ship canary", completed: true, completedAt: nil)

        XCTAssertEqual(renderCompletionMessage(item), "Todo completed: 7 - Ship canary")
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

import XCTest
@testable import TodoCLI
import TodoCore

final class TodoCLITests: XCTestCase {
    func testRenderCompletionMessageUsesStableFormat() {
        let item = TodoItem(id: "7", title: "Ship canary", completed: true, completedAt: nil)

        XCTAssertEqual(renderCompletionMessage(item), "Todo completed: 7 - Ship canary")
    }
}

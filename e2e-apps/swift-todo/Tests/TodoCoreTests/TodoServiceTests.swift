import XCTest
@testable import TodoCore

final class TodoServiceTests: XCTestCase {
    func testCreateTrimsTitleAndAssignsID() throws {
        let service = TodoService()

        let first = try service.create(title: "  Ship release  ")
        let second = try service.create(title: "Harden retries")

        XCTAssertEqual(first.id, "1")
        XCTAssertEqual(first.title, "Ship release")
        XCTAssertEqual(second.id, "2")
    }

    func testCompleteMarksItemDoneAndSetsCompletedAt() throws {
        let service = TodoService()
        let created = try service.create(title: "Fix stale branch handling")

        let completed = try service.complete(id: created.id)

        XCTAssertTrue(completed.completed)
        XCTAssertNotNil(completed.completedAt)
    }

    func testCompleteThrowsWhenItemMissing() throws {
        let service = TodoService()

        XCTAssertThrowsError(try service.complete(id: "404")) { error in
            XCTAssertEqual(error as? TodoServiceError, .itemNotFound)
        }
    }
}

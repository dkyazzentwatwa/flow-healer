import Foundation

public struct TodoItem: Equatable {
    public let id: String
    public var title: String
    public var completed: Bool
    public var completedAt: Date?

    public init(id: String, title: String, completed: Bool = false, completedAt: Date? = nil) {
        self.id = id
        self.title = title
        self.completed = completed
        self.completedAt = completedAt
    }
}

public enum TodoServiceError: Error, Equatable {
    case titleRequired
    case itemNotFound(id: String)
}

public final class TodoService {
    private var items: [TodoItem] = []
    private var nextID: Int = 1

    public init() {}

    public func list() -> [TodoItem] {
        items
    }

    public func create(title: String) throws -> TodoItem {
        let normalized = title.trimmingCharacters(in: .whitespacesAndNewlines)
        if normalized.isEmpty {
            throw TodoServiceError.titleRequired
        }

        let item = TodoItem(id: String(nextID), title: normalized)
        nextID += 1
        items.append(item)
        return item
    }

    public func complete(id: String) throws -> TodoItem {
        guard let index = items.firstIndex(where: { $0.id == id }) else {
            throw TodoServiceError.itemNotFound(id: id)
        }
        if !items[index].completed {
            items[index].completed = true
            items[index].completedAt = Date()
        }
        return items[index]
    }
}

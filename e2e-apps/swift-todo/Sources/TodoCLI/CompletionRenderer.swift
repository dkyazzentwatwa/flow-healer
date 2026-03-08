import Foundation
import TodoCore

func renderCompletionMessage(_ item: TodoItem) -> String {
    "Todo completed: \(item.id) - \(item.title)"
}

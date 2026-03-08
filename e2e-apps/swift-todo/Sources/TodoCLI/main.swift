import Foundation
import TodoCore

let service = TodoService()

do {
    _ = try service.create(title: "Stabilize merge queue")
    let created = try service.create(title: "Review auto-requeue metrics")
    let completed = try service.complete(id: created.id)
    print(renderCompletionMessage(completed))
} catch {
    print("Todo CLI failed: \(error)")
    exit(1)
}

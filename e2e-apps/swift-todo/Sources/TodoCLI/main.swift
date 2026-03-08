import Darwin
import Foundation
import TodoCore

private func writeLine(_ message: String) {
    print(message)
}

func normalizeTodoTitle(_ title: String) -> String {
    title
        .trimmingCharacters(in: .whitespacesAndNewlines)
        .components(separatedBy: .whitespacesAndNewlines)
        .filter { !$0.isEmpty }
        .joined(separator: " ")
}

func renderStableCompletionSummary(_ item: TodoItem) -> String {
    let summaryItem = TodoItem(
        id: item.id,
        title: normalizeTodoTitle(item.title),
        completed: item.completed,
        completedAt: item.completedAt
    )
    return renderCompletionMessage(summaryItem)
}

func runTodoCLI(
    service: TodoService,
    output: (String) -> Void,
    errorOutput: (String) -> Void
) -> Int32 {
    do {
        _ = try service.create(title: "Stabilize merge queue")
        let created = try service.create(title: "Review auto-requeue metrics")
        let completed = try service.complete(id: created.id)
        output(renderStableCompletionSummary(completed))
        return 0
    } catch {
        errorOutput("Todo CLI failed: \(error)")
        return 1
    }
}

func runTodoCLI() -> Int32 {
    runTodoCLI(
        service: TodoService(),
        output: writeLine,
        errorOutput: writeLine
    )
}

exit(runTodoCLI())

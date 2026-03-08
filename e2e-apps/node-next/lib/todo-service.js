export class TodoService {
  constructor() {
    this._todos = [];
    this._nextId = 1;
  }

  list() {
    return this._todos.map((todo) => ({ ...todo }));
  }

  create(title) {
    const normalized = normalizeTodoTitle(title);
    const todo = {
      id: String(this._nextId++),
      title: normalized,
      completed: false,
      createdAt: new Date().toISOString(),
      completedAt: null,
    };
    this._todos.push(todo);
    return { ...todo };
  }

  complete(id) {
    const key = String(id || "").trim();
    const todo = this._todos.find((item) => item.id === key);
    if (!todo) {
      return null;
    }
    if (!todo.completed) {
      todo.completed = true;
      todo.completedAt = new Date().toISOString();
    }
    return { ...todo };
  }
}

export function normalizeTodoTitle(title) {
  if (typeof title !== "string") {
    throw new Error("title_required");
  }

  const normalized = title.trim();
  if (!normalized) {
    throw new Error("title_required");
  }

  return normalized;
}

export const todoService = new TodoService();

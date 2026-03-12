export class TodoService {
  constructor(todos = []) {
    this._todos = todos.map((todo) => ({
      ...todo,
      id: normalizeTodoId(todo?.id),
      completed: normalizeCompletedFlag(todo?.completed),
      completedAt: normalizeCompletedFlag(todo?.completed) ? todo?.completedAt ?? null : null,
    }));
    this._nextId = getNextTodoId(this._todos);
  }

  list() {
    return this._todos.map((todo) => ({ ...todo }));
  }

  create(title) {
    const normalized = normalizeTodoTitle(title);
    this._nextId = Math.max(this._nextId, getNextTodoId(this._todos));
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
    const key = normalizeTodoId(id);
    const todo = this._todos.find((item) => normalizeTodoId(item.id) === key);
    if (!todo) {
      return null;
    }
    if (!todo.completed) {
      todo.completed = true;
      todo.completedAt = new Date().toISOString();
    } else if (!todo.completedAt) {
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

function getNextTodoId(todos) {
  let maxId = 0;

  for (const todo of todos) {
    const rawId = normalizeTodoId(todo?.id);
    if (!/^-?\d+$/.test(rawId)) {
      continue;
    }
    const numericId = Number.parseInt(rawId, 10);
    if (Number.isSafeInteger(numericId) && numericId > maxId) {
      maxId = numericId;
    }
  }

  return maxId + 1;
}

function normalizeTodoId(value) {
  const normalized = String(value ?? "").trim();
  const unsigned = normalized.startsWith("+") ? normalized.slice(1) : normalized;

  if (!/^-?\d+$/.test(unsigned)) {
    return unsigned;
  }

  const numericId = Number.parseInt(unsigned, 10);
  if (Number.isSafeInteger(numericId)) {
    return String(numericId);
  }

  return unsigned;
}

function normalizeCompletedFlag(value) {
  if (value === true) {
    return true;
  }

  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    return normalized === "true" || normalized === "1";
  }

  return value === 1;
}

export function toPublicTodo(todo) {
  return {
    id: Number(todo.id),
    title: todo.title,
    completed: todo.completed,
  };
}

export function toPublicTodoList(todos) {
  return todos.map((todo) => toPublicTodo(todo));
}

export function toTodoListPayload(todos) {
  return { todos: toPublicTodoList(todos) };
}

export function toTodoItemPayload(todo) {
  return { item: toPublicTodo(todo) };
}

export const todoService = new TodoService();

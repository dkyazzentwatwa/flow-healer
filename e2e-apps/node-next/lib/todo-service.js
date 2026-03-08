const defaultTodos = [
  {
    id: "1",
    title: "Ship stable completion endpoint",
    completed: false,
    completedAt: null,
  },
  {
    id: "2",
    title: "Keep repeated calls idempotent",
    completed: false,
    completedAt: null,
  },
];

let todos = defaultTodos.map((todo) => ({ ...todo }));

function cloneTodo(todo) {
  return { ...todo };
}

function buildCompletedTodo(todo) {
  return {
    ...todo,
    completed: true,
    completedAt: todo.completedAt ?? new Date().toISOString(),
  };
}

function hasStableCompletionState(todo) {
  return todo.completed && todo.completedAt !== null;
}

export function listTodos() {
  return todos.map(cloneTodo);
}

export function completeTodo(id) {
  const todoIndex = todos.findIndex((entry) => entry.id === id);

  if (todoIndex === -1) {
    return null;
  }

  if (hasStableCompletionState(todos[todoIndex])) {
    return cloneTodo(todos[todoIndex]);
  }

  const completedTodo = buildCompletedTodo(todos[todoIndex]);
  todos[todoIndex] = completedTodo;

  return cloneTodo(completedTodo);
}

export function resetTodosForTests(seed = defaultTodos) {
  todos = seed.map((todo) => cloneTodo(todo));
}

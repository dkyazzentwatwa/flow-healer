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

export function listTodos() {
  return todos.map(cloneTodo);
}

export function completeTodo(id) {
  const todo = todos.find((entry) => entry.id === id);

  if (!todo) {
    return null;
  }

  if (!todo.completed) {
    todo.completed = true;
    todo.completedAt = new Date().toISOString();
  }

  return cloneTodo(todo);
}

export function resetTodosForTests(seed = defaultTodos) {
  todos = seed.map((todo) => cloneTodo(todo));
}

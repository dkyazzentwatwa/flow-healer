const todos = [
  {
    id: 1,
    title: 'Ship stable list endpoint contract coverage',
    completed: false,
  },
  {
    id: 2,
    title: 'Keep todo payloads flexible as data evolves',
    completed: true,
  },
];

export function listTodos() {
  return todos.map((todo) => ({ ...todo }));
}

export async function GET() {
  return Response.json({
    todos: listTodos(),
  });
}

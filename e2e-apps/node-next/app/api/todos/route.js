import { todoService } from "../../../lib/todo-service.js";

export function listTodos() {
  return todoService.list().map((todo) => ({
    id: Number(todo.id),
    title: todo.title,
    completed: todo.completed,
  }));
}

export async function GET() {
  return Response.json({ todos: listTodos() }, { status: 200 });
}

export async function POST(request) {
  let payload = {};
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "invalid_json" }, { status: 400 });
  }
  if (!payload || typeof payload !== "object" || typeof payload.title !== "string") {
    return Response.json({ error: "title_required" }, { status: 400 });
  }
  try {
    const created = todoService.create(payload.title);
    return Response.json({ item: created }, { status: 201 });
  } catch (error) {
    return Response.json({ error: String(error.message || "create_failed") }, { status: 400 });
  }
}

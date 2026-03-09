import {
  normalizeTodoTitle,
  toTodoItemPayload,
  toTodoListPayload,
  todoService,
} from "../../../lib/todo-service.js";

export function listTodos() {
  return toTodoListPayload(todoService.list()).todos;
}

export async function GET() {
  return Response.json(toTodoListPayload(todoService.list()), { status: 200 });
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
    const created = todoService.create(normalizeTodoTitle(payload.title));
    return Response.json(toTodoItemPayload(created), { status: 201 });
  } catch (error) {
    return Response.json({ error: String(error.message || "create_failed") }, { status: 400 });
  }
}

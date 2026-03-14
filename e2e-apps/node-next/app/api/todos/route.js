import {
  isTodoPayload,
  toTodoItemPayload,
  toTodoListPayload,
  todoService,
} from "../../../lib/todo-service.js";

export function listTodos() {
  return toTodoListPayload(todoService.list()).todos;
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
  if (!isTodoPayload(payload)) {
    return Response.json({ error: "invalid_payload" }, { status: 400 });
  }

  try {
    const created = todoService.create(payload.title);
    return Response.json(toTodoItemPayload(created), { status: 201 });
  } catch (error) {
    return Response.json(
      { error: String(error?.message) === "title_required" ? "title_required" : "create_failed" },
      { status: 400 },
    );
  }
}

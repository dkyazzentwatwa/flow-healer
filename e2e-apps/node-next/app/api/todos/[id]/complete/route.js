import { todoService, toPublicTodo } from "../../../../../lib/todo-service.js";

export async function POST(_request, context) {
  const item = todoService.complete(context?.params?.id || "");
  if (!item) {
    return Response.json({ error: "not_found" }, { status: 404 });
  }
  return Response.json({ item: toPublicTodo(item) }, { status: 200 });
}

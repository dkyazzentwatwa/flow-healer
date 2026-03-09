import { todoService, toPublicTodo } from "../../../../../lib/todo-service.js";

export async function POST(_request, context) {
  const params = await context?.params;
  const item = todoService.complete(params?.id ?? "");
  if (!item) {
    return Response.json({ error: "not_found" }, { status: 404 });
  }
  return Response.json({ item: toPublicTodo(item) }, { status: 200 });
}

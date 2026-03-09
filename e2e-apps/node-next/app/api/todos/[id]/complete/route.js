import { todoService, toPublicTodo } from "../../../../../lib/todo-service.js";

export async function POST(_request, context) {
  const item = todoService.complete(await resolveTodoId(context));
  if (!item) {
    return Response.json({ error: "not_found" }, { status: 404 });
  }
  return Response.json({ item: toPublicTodo(item) }, { status: 200 });
}

async function resolveTodoId(context) {
  const params = await context?.params;
  const rawId = Array.isArray(params?.id) ? params.id[0] : params?.id;
  return String(rawId ?? "").trim();
}

import { completeTodo } from "../../../../../lib/todo-service.js";

function json(body, init) {
  return new Response(JSON.stringify(body), {
    headers: {
      "content-type": "application/json",
    },
    ...init,
  });
}

export async function POST(_request, { params }) {
  const todo = completeTodo(params.id);

  if (!todo) {
    return json({ error: "Todo not found" }, { status: 404 });
  }

  return json({ todo }, { status: 200 });
}

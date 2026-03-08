import { completeTodo } from "../../../../../lib/todo-service.js";

function json(body, init) {
  return new Response(JSON.stringify(body), {
    headers: {
      "content-type": "application/json",
    },
    ...init,
  });
}

async function resolveParams(params) {
  return Promise.resolve(params);
}

export async function POST(_request, { params }) {
  const { id } = await resolveParams(params);
  const completedTodo = completeTodo(id);

  if (!completedTodo) {
    return json({ error: "Todo not found" }, { status: 404 });
  }

  return json({ todo: completedTodo }, { status: 200 });
}

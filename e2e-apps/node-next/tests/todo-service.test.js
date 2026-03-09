import test from "node:test";
import assert from "node:assert/strict";

import { GET, POST, listTodos } from "../app/api/todos/route.js";
import { POST as completeTodo } from "../app/api/todos/[id]/complete/route.js";
import {
  TodoService,
  toPublicTodo,
  toPublicTodoList,
  toTodoItemPayload,
  toTodoListPayload,
} from "../lib/todo-service.js";

test("listTodos returns todo objects with the stable fields the API exposes", () => {
  const todos = listTodos();

  assert.ok(Array.isArray(todos));

  for (const todo of todos) {
    assert.deepEqual(Object.keys(todo).sort(), ["completed", "id", "title"]);
    assert.equal(typeof todo.id, "number");
    assert.equal(typeof todo.title, "string");
    assert.equal(typeof todo.completed, "boolean");
  }
});

test("GET returns the stable list endpoint contract", async () => {
  const response = await GET();

  assert.equal(response.status, 200);
  assert.equal(response.headers.get("content-type"), "application/json");

  const payload = await response.json();

  assert.deepEqual(Object.keys(payload), ["todos"]);
  assert.ok(Array.isArray(payload.todos));
  assert.deepEqual(payload.todos, listTodos());
});

test("create assigns ids and trims title", () => {
  const service = new TodoService();
  const first = service.create("  Ship dashboard  ");
  const second = service.create("Fix flaky retries");

  assert.equal(first.id, "1");
  assert.equal(first.title, "Ship dashboard");
  assert.equal(second.id, "2");
});

test("create advances past the highest existing todo id", () => {
  const service = new TodoService([
    {
      id: "2",
      title: "Already there",
      completed: false,
      createdAt: "2026-03-08T12:00:00.000Z",
      completedAt: null,
    },
    {
      id: "7",
      title: "Highest id wins",
      completed: true,
      createdAt: "2026-03-08T12:01:00.000Z",
      completedAt: "2026-03-08T12:02:00.000Z",
    },
  ]);

  const created = service.create("Add the next item");

  assert.equal(created.id, "8");
  assert.deepEqual(
    service.list().map((todo) => todo.id),
    ["2", "7", "8"],
  );
});

test("complete marks an item complete and records completedAt", () => {
  const service = new TodoService();
  const created = service.create("Harden retries");
  const completed = service.complete(created.id);

  assert.equal(completed?.completed, true);
  assert.ok(completed?.completedAt);
});

test("complete is idempotent for already-completed items", () => {
  const service = new TodoService();
  const created = service.create("Avoid duplicate side effects");
  const firstCompletion = service.complete(created.id);
  const secondCompletion = service.complete(created.id);

  assert.equal(secondCompletion?.completed, true);
  assert.equal(secondCompletion?.completedAt, firstCompletion?.completedAt);
});

test("list returns a defensive copy to prevent mutation leaks", () => {
  const service = new TodoService();
  service.create("Run canary");

  const listed = service.list();
  listed[0].title = "mutated";

  assert.equal(service.list()[0].title, "Run canary");
});

test("create rejects blank and non-string titles", () => {
  const service = new TodoService();

  assert.throws(() => service.create("   "), /title_required/);
  assert.throws(() => service.create({ text: "Ship it" }), /title_required/);
});

test("toPublicTodo strips internal fields and normalizes the id type", () => {
  assert.deepEqual(
    toPublicTodo({
      id: "7",
      title: "Ship it",
      completed: true,
      createdAt: "2026-03-08T12:00:00.000Z",
      completedAt: "2026-03-08T12:05:00.000Z",
    }),
    {
      id: 7,
      title: "Ship it",
      completed: true,
    },
  );
});

test("todo payload helpers keep the collection and item route shape stable", () => {
  const todos = [
    {
      id: "7",
      title: "Ship it",
      completed: true,
      createdAt: "2026-03-08T12:00:00.000Z",
      completedAt: "2026-03-08T12:05:00.000Z",
    },
  ];

  assert.deepEqual(toPublicTodoList(todos), [
    {
      id: 7,
      title: "Ship it",
      completed: true,
    },
  ]);
  assert.deepEqual(toTodoListPayload(todos), {
    todos: [
      {
        id: 7,
        title: "Ship it",
        completed: true,
      },
    ],
  });
  assert.deepEqual(toTodoItemPayload(todos[0]), {
    item: {
      id: 7,
      title: "Ship it",
      completed: true,
    },
  });
});

test("POST rejects blank and malformed titles", async () => {
  const todosBefore = listTodos().length;
  const blankResponse = await POST(
    new Request("http://localhost/api/todos", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ title: "  \n\t  " }),
    }),
  );
  const malformedResponse = await POST(
    new Request("http://localhost/api/todos", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ title: { text: "Ship it" } }),
    }),
  );

  assert.equal(blankResponse.status, 400);
  assert.deepEqual(await blankResponse.json(), { error: "title_required" });
  assert.equal(malformedResponse.status, 400);
  assert.deepEqual(await malformedResponse.json(), { error: "title_required" });
  assert.equal(listTodos().length, todosBefore);
});

test("POST returns the same stable public todo fields as GET", async () => {
  const response = await POST(
    new Request("http://localhost/api/todos", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ title: "  Ship stable payload  " }),
    }),
  );

  assert.equal(response.status, 201);
  assert.equal(response.headers.get("content-type"), "application/json");
  assert.deepEqual(await response.json(), {
    item: {
      id: listTodos().at(-1)?.id,
      title: "Ship stable payload",
      completed: false,
    },
  });
});

test("complete route returns the stable public todo fields", async () => {
  const createdResponse = await POST(
    new Request("http://localhost/api/todos", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ title: "Close the loop" }),
    }),
  );
  const createdPayload = await createdResponse.json();

  const response = await completeTodo(undefined, {
    params: { id: String(createdPayload.item.id) },
  });

  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {
    item: {
      id: createdPayload.item.id,
      title: "Close the loop",
      completed: true,
    },
  });
});

test("complete route stays idempotent across repeated requests", async () => {
  const createdResponse = await POST(
    new Request("http://localhost/api/todos", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ title: "Repeat the completion call" }),
    }),
  );
  const createdPayload = await createdResponse.json();
  const context = { params: Promise.resolve({ id: String(createdPayload.item.id) }) };

  const firstResponse = await completeTodo(undefined, context);
  const secondResponse = await completeTodo(undefined, context);

  assert.equal(firstResponse.status, 200);
  assert.equal(secondResponse.status, 200);
  assert.deepEqual(await secondResponse.json(), await firstResponse.json());
});

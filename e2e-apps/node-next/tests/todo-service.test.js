import test from "node:test";
import assert from "node:assert/strict";

import { GET, POST, listTodos } from "../app/api/todos/route.js";
import { TodoService } from "../lib/todo-service.js";

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

test("complete marks an item complete and records completedAt", () => {
  const service = new TodoService();
  const created = service.create("Harden retries");
  const completed = service.complete(created.id);

  assert.equal(completed?.completed, true);
  assert.ok(completed?.completedAt);
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

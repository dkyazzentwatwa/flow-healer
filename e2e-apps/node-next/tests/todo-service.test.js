import assert from "node:assert/strict";
import test from "node:test";

import { completeTodo, resetTodosForTests } from "../lib/todo-service.js";

test("completeTodo marks an incomplete todo complete", () => {
  resetTodosForTests([
    { id: "a", title: "One", completed: false, completedAt: null },
  ]);

  const todo = completeTodo("a");

  assert.equal(todo?.completed, true);
  assert.equal(typeof todo?.completedAt, "string");
});

test("completeTodo is stable when the same todo is completed repeatedly", () => {
  resetTodosForTests([
    { id: "a", title: "One", completed: false, completedAt: null },
  ]);

  const first = completeTodo("a");
  const second = completeTodo("a");

  assert.deepEqual(second, first);
});

test("completeTodo returns null when the todo does not exist", () => {
  resetTodosForTests([]);

  assert.equal(completeTodo("missing"), null);
});

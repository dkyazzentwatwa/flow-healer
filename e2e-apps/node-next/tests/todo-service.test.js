import assert from 'node:assert/strict';
import test from 'node:test';

import { GET, listTodos } from '../app/api/todos/route.js';

test('listTodos returns todo objects with the stable fields the API exposes', () => {
  const todos = listTodos();

  assert.ok(Array.isArray(todos));
  assert.ok(todos.length > 0);

  for (const todo of todos) {
    assert.deepEqual(Object.keys(todo).sort(), ['completed', 'id', 'title']);
    assert.equal(typeof todo.id, 'number');
    assert.equal(typeof todo.title, 'string');
    assert.equal(typeof todo.completed, 'boolean');
  }
});

test('GET returns the stable list endpoint contract', async () => {
  const response = await GET();

  assert.equal(response.status, 200);
  assert.equal(response.headers.get('content-type'), 'application/json');

  const payload = await response.json();

  assert.deepEqual(Object.keys(payload), ['todos']);
  assert.ok(Array.isArray(payload.todos));
  assert.deepEqual(payload.todos, listTodos());
});

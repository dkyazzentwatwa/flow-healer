import assert from 'node:assert/strict';
import test from 'node:test';

import getUserById, { listAllUsers } from '../src/users.js';

test('getUserById returns a user for a known id', () => {
  const user = getUserById(1);
  assert.equal(user.id, 1);
  assert.equal(user.name, 'Alice Nguyen');
});

test('getUserById returns the correct user for each seed id', () => {
  assert.equal(getUserById(2).name, 'Bob Okafor');
  assert.equal(getUserById(3).name, 'Carol Ferreira');
});

test('getUserById throws RangeError for an unknown id', () => {
  assert.throws(
    () => getUserById(99),
    { name: 'RangeError', message: 'No user found with id 99' },
  );
});

test('getUserById throws RangeError for id 0', () => {
  assert.throws(
    () => getUserById(0),
    { name: 'RangeError', message: 'No user found with id 0' },
  );
});

test('listAllUsers returns all three seed users', () => {
  const users = listAllUsers();
  assert.equal(users.length, 3);
  assert.deepEqual(users.map(u => u.id), [1, 2, 3]);
});

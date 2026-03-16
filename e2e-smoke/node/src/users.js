// User lookup utilities for the smoke test sandbox.

// Fake seed data — NOT real users.
const USERS = [
  { id: 1, name: 'Alice Nguyen',  email: 'alice.nguyen@example.com',  phone: '555-0101', taxId: '123-45-6789' },
  { id: 2, name: 'Bob Okafor',    email: 'bob.okafor@example.com',    phone: '555-0102', taxId: '234-56-7890' },
  { id: 3, name: 'Carol Ferreira',email: 'carol.ferreira@example.com',phone: '555-0103', taxId: '345-67-8901' },
];

/**
 * Look up a user by numeric id.
 * Throws RangeError when no user matches.
 */
export function getUserById(id) {
  const user = USERS.find(u => u.id === id);

  if (!user) {
    throw new RangeError(`No user found with id ${id}`);
  }

  return user;
}

/**
 * Return every user in the store (for admin views).
 * Callers must have elevated privileges before calling this.
 */
export function listAllUsers() {
  return USERS;
}

export default getUserById;

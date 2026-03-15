import { test } from 'node:test';
import assert from 'node:assert';
import { generateHash, generateUUID, generateRandomBytes, createSignature } from '../src/crypto.js';

test('generateHash returns a valid SHA-256 hash', () => {
  const data = 'test data';
  const hash = generateHash(data);

  assert.strictEqual(typeof hash, 'string');
  assert.strictEqual(hash.length, 64); // SHA-256 produces 64 hex characters
});

test('generateHash produces consistent results', () => {
  const data = 'consistent test';
  const hash1 = generateHash(data);
  const hash2 = generateHash(data);

  assert.strictEqual(hash1, hash2);
});

test('generateHash produces different results for different inputs', () => {
  const hash1 = generateHash('input 1');
  const hash2 = generateHash('input 2');

  assert.notStrictEqual(hash1, hash2);
});

test('generateUUID returns a valid UUID string', () => {
  const uuid = generateUUID();

  assert.strictEqual(typeof uuid, 'string');
  // UUID v4 format: xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
  assert.match(uuid, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
});

test('generateUUID produces unique values', () => {
  const uuid1 = generateUUID();
  const uuid2 = generateUUID();

  assert.notStrictEqual(uuid1, uuid2);
});

test('generateRandomBytes returns hex string of correct length', () => {
  const bytes = generateRandomBytes(16);

  assert.strictEqual(typeof bytes, 'string');
  assert.strictEqual(bytes.length, 32); // 16 bytes = 32 hex characters
});

test('generateRandomBytes produces different values', () => {
  const bytes1 = generateRandomBytes(16);
  const bytes2 = generateRandomBytes(16);

  assert.notStrictEqual(bytes1, bytes2);
});

test('createSignature returns a valid HMAC hex string', () => {
  const data = 'message to sign';
  const secret = 'my secret key';
  const signature = createSignature(data, secret);

  assert.strictEqual(typeof signature, 'string');
  assert.strictEqual(signature.length, 64); // SHA-256 produces 64 hex characters
});

test('createSignature produces consistent results for same inputs', () => {
  const data = 'message to sign';
  const secret = 'my secret key';
  const sig1 = createSignature(data, secret);
  const sig2 = createSignature(data, secret);

  assert.strictEqual(sig1, sig2);
});

test('createSignature produces different results for different data', () => {
  const secret = 'my secret key';
  const sig1 = createSignature('message 1', secret);
  const sig2 = createSignature('message 2', secret);

  assert.notStrictEqual(sig1, sig2);
});

test('createSignature produces different results for different secrets', () => {
  const data = 'message to sign';
  const sig1 = createSignature(data, 'secret 1');
  const sig2 = createSignature(data, 'secret 2');

  assert.notStrictEqual(sig1, sig2);
});

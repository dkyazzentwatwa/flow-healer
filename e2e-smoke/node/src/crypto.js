import crypto from 'node:crypto';

/**
 * Generate a random hash using SHA-256 algorithm.
 * Uses the modern Node.js crypto API with node: prefix for better ESM support.
 */
export function generateHash(data) {
  const hash = crypto.createHash('sha256');
  hash.update(data);
  return hash.digest('hex');
}

/**
 * Generate a random UUID using the crypto module.
 */
export function generateUUID() {
  return crypto.randomUUID();
}

/**
 * Generate random bytes of specified length.
 */
export function generateRandomBytes(length) {
  return crypto.randomBytes(length).toString('hex');
}

/**
 * Create an HMAC signature for data.
 */
export function createSignature(data, secret) {
  const hmac = crypto.createHmac('sha256', secret);
  hmac.update(data);
  return hmac.digest('hex');
}

export default {
  generateHash,
  generateUUID,
  generateRandomBytes,
  createSignature,
};

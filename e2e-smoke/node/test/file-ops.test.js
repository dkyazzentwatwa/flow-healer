import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile, writeFile, mkdir, chmod, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { readSandboxFile, writeSandboxFile, readSandboxJSON, writeSandboxJSON } from '../src/file-ops.js';

const testDir = join(tmpdir(), `file-ops-test-${Date.now()}-${Math.random()}`);

test.before(async () => {
  await mkdir(testDir, { recursive: true });
});

test.after(async () => {
  try {
    await rm(testDir, { recursive: true, force: true });
  } catch {
    // Cleanup errors are non-fatal
  }
});

test('readSandboxFile reads a valid file successfully', async () => {
  const testFile = join(testDir, 'test.txt');
  const expectedContent = 'Hello, World!';

  await writeFile(testFile, expectedContent, 'utf-8');

  const content = await readSandboxFile(testFile);
  assert.equal(content, expectedContent);
});

test('readSandboxFile throws on missing file (ENOENT)', async () => {
  const nonexistentFile = join(testDir, 'nonexistent.txt');

  await assert.rejects(
    () => readSandboxFile(nonexistentFile),
    (error) => error.message.includes('File not found'),
  );
});

test('writeSandboxFile writes content successfully', async () => {
  const testFile = join(testDir, 'write-test.txt');
  const content = 'Test content';

  await writeSandboxFile(testFile, content);

  const readContent = await readFile(testFile, 'utf-8');
  assert.equal(readContent, content);
});

test('writeSandboxFile throws on permission denied (EACCES)', async () => {
  const testFile = join(testDir, 'readonly.txt');

  // Create a file with no write permissions
  await writeFile(testFile, 'initial content', 'utf-8');
  await chmod(testFile, 0o444); // read-only

  await assert.rejects(
    () => writeSandboxFile(testFile, 'new content'),
    (error) => error.message.includes('Permission denied'),
  );

  // Restore permissions for cleanup
  await chmod(testFile, 0o644);
});

test('writeSandboxFile throws when parent directory does not exist', async () => {
  const nonexistentDir = join(testDir, 'nonexistent', 'nested', 'dir');
  const testFile = join(nonexistentDir, 'file.txt');

  await assert.rejects(
    () => writeSandboxFile(testFile, 'content'),
    (error) => error.message.includes('Parent directory not found') || error.message.includes('ENOENT'),
  );
});

test('readSandboxJSON parses valid JSON file', async () => {
  const testFile = join(testDir, 'test.json');
  const jsonData = { name: 'test', value: 42 };

  await writeFile(testFile, JSON.stringify(jsonData), 'utf-8');

  const parsedData = await readSandboxJSON(testFile);
  assert.deepEqual(parsedData, jsonData);
});

test('readSandboxJSON throws on invalid JSON', async () => {
  const testFile = join(testDir, 'invalid.json');
  const invalidJSON = '{ invalid json content ]';

  await writeFile(testFile, invalidJSON, 'utf-8');

  await assert.rejects(
    () => readSandboxJSON(testFile),
    (error) => error.message.includes('Invalid JSON'),
  );
});

test('writeSandboxJSON writes JSON data correctly', async () => {
  const testFile = join(testDir, 'write-json.json');
  const jsonData = { user: 'alice', id: 123 };

  await writeSandboxJSON(testFile, jsonData);

  const readContent = await readFile(testFile, 'utf-8');
  const parsedData = JSON.parse(readContent);
  assert.deepEqual(parsedData, jsonData);
});

test('readSandboxFile handles error logging without throwing on missing file message', async () => {
  const nonexistentFile = join(testDir, 'missing-file.txt');

  try {
    await readSandboxFile(nonexistentFile);
    assert.fail('Should have thrown an error');
  } catch (error) {
    assert.ok(error instanceof Error);
    assert.ok(error.message.includes('File not found'));
  }
});

test('writeSandboxFile handles error logging without throwing on permission error', async () => {
  const testFile = join(testDir, 'protected.txt');

  await writeFile(testFile, 'initial', 'utf-8');
  await chmod(testFile, 0o444);

  try {
    await writeSandboxFile(testFile, 'modified');
    assert.fail('Should have thrown an error');
  } catch (error) {
    assert.ok(error instanceof Error);
    assert.ok(error.message.includes('Permission denied'));
  } finally {
    await chmod(testFile, 0o644);
  }
});

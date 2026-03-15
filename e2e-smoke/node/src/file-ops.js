import { readFile, writeFile } from 'node:fs/promises';

/**
 * Safely read a file from the sandbox directory.
 * Handles ENOENT (file not found) and EACCES (permission denied) errors gracefully.
 */
export async function readSandboxFile(filepath) {
  try {
    const content = await readFile(filepath, 'utf-8');
    return content;
  } catch (error) {
    if (error.code === 'ENOENT') {
      console.error(`File not found: ${filepath}`);
      throw new Error(`File not found: ${filepath}`);
    }
    if (error.code === 'EACCES') {
      console.error(`Permission denied reading file: ${filepath}`);
      throw new Error(`Permission denied: ${filepath}`);
    }
    console.error(`Error reading file ${filepath}:`, error.message);
    throw error;
  }
}

/**
 * Safely write content to a file in the sandbox directory.
 * Handles ENOENT (parent directory not found) and EACCES (permission denied) errors gracefully.
 */
export async function writeSandboxFile(filepath, content) {
  try {
    await writeFile(filepath, content, 'utf-8');
    return filepath;
  } catch (error) {
    if (error.code === 'ENOENT') {
      console.error(`Parent directory not found for file: ${filepath}`);
      throw new Error(`Parent directory not found: ${filepath}`);
    }
    if (error.code === 'EACCES') {
      console.error(`Permission denied writing file: ${filepath}`);
      throw new Error(`Permission denied: ${filepath}`);
    }
    console.error(`Error writing file ${filepath}:`, error.message);
    throw error;
  }
}

/**
 * Safely read and parse a JSON file from the sandbox directory.
 */
export async function readSandboxJSON(filename) {
  try {
    const content = await readSandboxFile(filename);
    return JSON.parse(content);
  } catch (error) {
    if (error instanceof SyntaxError) {
      console.error(`Invalid JSON in file: ${filename}`);
      throw new Error(`Invalid JSON in file: ${filename}`);
    }
    throw error;
  }
}

/**
 * Safely write JSON content to a file in the sandbox directory.
 */
export async function writeSandboxJSON(filename, data) {
  try {
    const content = JSON.stringify(data, null, 2);
    return await writeSandboxFile(filename, content);
  } catch (error) {
    console.error(`Error writing JSON to file ${filename}:`, error.message);
    throw error;
  }
}

import test from "node:test";
import assert from "node:assert/strict";

import { add } from "./add.mjs";

test("add sums two numbers", () => {
  assert.equal(add(2, 3), 5);
});

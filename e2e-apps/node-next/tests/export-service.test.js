import test from "node:test";
import assert from "node:assert/strict";

import {
  escapeCsvValue,
  toCsvRows,
  toTodoCsv,
} from "../lib/export-service.js";

test("escapeCsvValue quotes values that contain csv control characters", () => {
  assert.equal(escapeCsvValue("Roadmap"), "Roadmap");
  assert.equal(escapeCsvValue("Needs, review"), "\"Needs, review\"");
  assert.equal(escapeCsvValue("He said \"ship it\""), "\"He said \"\"ship it\"\"\"");
  assert.equal(escapeCsvValue("Line one\nLine two"), "\"Line one\nLine two\"");
});

test("toCsvRows keeps a stable header row and serializes values in order", () => {
  assert.deepEqual(
    toCsvRows(
      [
        {
          id: 7,
          title: "Ship dashboard",
          completed: true,
        },
      ],
      ["id", "title", "completed"],
    ),
    ["id,title,completed", "7,Ship dashboard,true"],
  );
});

test("toTodoCsv exports todos with stable columns and escaped values", () => {
  assert.equal(
    toTodoCsv([
      {
        id: "1",
        title: "Review, \"export\"\nnotes",
        completed: false,
      },
      {
        id: 2,
        title: "Ship CSV",
        completed: true,
      },
    ]),
    [
      "id,title,completed",
      "1,\"Review, \"\"export\"\"\nnotes\",false",
      "2,Ship CSV,true",
    ].join("\n"),
  );
});

test("toTodoCsv returns only the header row for an empty list", () => {
  assert.equal(toTodoCsv([]), "id,title,completed");
});

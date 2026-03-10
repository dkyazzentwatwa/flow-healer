import test from "node:test";
import assert from "node:assert/strict";

import { GET } from "../app/api/auth/session/route.js";

test("GET returns an unauthenticated session payload when the session cookie is missing", async () => {
  const response = await GET(new Request("http://localhost/api/auth/session"));

  assert.equal(response.status, 200);
  assert.equal(response.headers.get("content-type"), "application/json");
  assert.deepEqual(await response.json(), {
    authenticated: false,
    session: null,
  });
});

test("GET returns the normalized session payload from an encoded session cookie", async () => {
  const response = await GET(
    new Request("http://localhost/api/auth/session", {
      headers: {
        cookie: `session=${encodeURIComponent(
          JSON.stringify({
            user: {
              name: "Taylor",
              email: "taylor@example.com",
              image: "https://example.com/avatar.png",
            },
            expires: "2026-03-10T12:00:00.000Z",
          }),
        )}`,
      },
    }),
  );

  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {
    authenticated: true,
    session: {
      user: {
        name: "Taylor",
        email: "taylor@example.com",
        image: "https://example.com/avatar.png",
      },
      expires: "2026-03-10T12:00:00.000Z",
    },
  });
});

test("GET ignores malformed session cookies instead of throwing", async () => {
  const response = await GET(
    new Request("http://localhost/api/auth/session", {
      headers: {
        cookie: "session=%E0%A4%A",
      },
    }),
  );

  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {
    authenticated: false,
    session: null,
  });
});

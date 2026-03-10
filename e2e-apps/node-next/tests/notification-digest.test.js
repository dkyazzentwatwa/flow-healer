import test from "node:test";
import assert from "node:assert/strict";

import { flushRecipientDigest } from "../lib/notification-digest.js";

test("flushRecipientDigest leaves another recipient's queued notification untouched when ids collide", () => {
  const queuedNotifications = [
    {
      id: "shared-id",
      recipient: "alex@example.com",
      title: "Build finished",
      message: "The nightly build completed.",
      createdAt: "2026-03-10T08:00:00.000Z",
      sent: false,
    },
    {
      id: "shared-id",
      recipient: "blair@example.com",
      title: "Build finished",
      message: "The nightly build completed.",
      createdAt: "2026-03-10T08:00:00.000Z",
      sent: false,
    },
  ];

  const result = flushRecipientDigest(queuedNotifications, "alex@example.com");

  assert.equal(result.digest.recipient, "alex@example.com");
  assert.equal(result.digest.notifications.length, 1);
  assert.equal(result.notifications[0].sent, true);
  assert.equal(result.notifications[1].sent, false);
});

test("flushRecipientDigest with maxItems marks only the included notification instances as sent", () => {
  const queuedNotifications = [
    {
      id: "shared-id",
      recipient: "alex@example.com",
      title: "Build finished",
      message: "The nightly build completed.",
      createdAt: "2026-03-10T08:00:00.000Z",
      sent: false,
    },
    {
      id: "shared-id",
      recipient: "alex@example.com",
      title: "Build finished",
      message: "The nightly build completed.",
      createdAt: "2026-03-10T08:00:00.000Z",
      sent: false,
    },
    {
      id: "shared-id",
      recipient: "blair@example.com",
      title: "Build finished",
      message: "The nightly build completed.",
      createdAt: "2026-03-10T08:00:00.000Z",
      sent: false,
    },
  ];

  const result = flushRecipientDigest(queuedNotifications, "alex@example.com", {
    maxItems: 1,
  });

  assert.equal(result.digest.notifications.length, 1);
  assert.equal(result.notifications[0].sent, true);
  assert.equal(result.notifications[1].sent, false);
  assert.equal(result.notifications[2].sent, false);
});

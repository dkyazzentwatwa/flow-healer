import test from "node:test";
import assert from "node:assert/strict";

import { buildRecipientDigest, flushRecipientDigest } from "../lib/notification-digest.js";

test("buildRecipientDigest groups queued notifications per recipient", () => {
  const notifications = [
    { id: "1", recipient: "alice@example.com", subject: "A", status: "queued" },
    { id: "2", recipient: "alice@example.com", subject: "B", status: "sent" },
    { id: "3", recipient: "bob@example.com", subject: "C", status: "queued" },
  ];

  const digest = buildRecipientDigest(notifications);

  assert.deepEqual(digest, [
    {
      recipient: "alice@example.com",
      entries: [
        {
          id: "1",
          recipient: "alice@example.com",
          subject: "A",
          body: "",
          createdAt: "",
        },
      ],
    },
    {
      recipient: "bob@example.com",
      entries: [
        {
          id: "3",
          recipient: "bob@example.com",
          subject: "C",
          body: "",
          createdAt: "",
        },
      ],
    },
  ]);
});

test("flushRecipientDigest marks only recipient-scoped ids as sent", () => {
  const notifications = [
    { id: "42", recipient: "alice@example.com", subject: "A", status: "queued" },
    { id: "42", recipient: "bob@example.com", subject: "B", status: "queued" },
    { id: "43", recipient: "alice@example.com", subject: "C", status: "queued" },
  ];

  const result = flushRecipientDigest(notifications, "alice@example.com", {
    sentAt: "2026-03-10T10:20:30Z",
  });

  assert.equal(result.recipient, "alice@example.com");
  assert.equal(result.sent, 2);
  assert.deepEqual(result.sentIds.sort(), ["42", "43"]);

  assert.equal(notifications[0].status, "sent");
  assert.equal(notifications[0].sentAt, "2026-03-10T10:20:30Z");
  assert.equal(notifications[1].status, "queued");
  assert.equal(notifications[1].sentAt, undefined);
  assert.equal(notifications[2].status, "sent");
  assert.equal(notifications[2].sentAt, "2026-03-10T10:20:30Z");
});

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

<<<<<<< HEAD
function normalizeMaxItems(maxItems, totalItems) {
  if (!Number.isFinite(maxItems) || maxItems <= 0) {
    return totalItems;
  }

  return Math.min(Math.floor(maxItems), totalItems);
}

function cloneNotification(notification, sent) {
  return {
    ...notification,
    sent,
  };
}

export function flushRecipientDigest(notifications, recipient, options = {}) {
  const queuedEntries = notifications
    .map((notification, index) => ({ notification, index }))
    .filter(
      ({ notification }) =>
        notification?.recipient === recipient && notification?.sent !== true,
    );

  const maxItems = normalizeMaxItems(options.maxItems, queuedEntries.length);
  const selectedEntries = queuedEntries.slice(0, maxItems);
  const selectedIndexes = new Set(selectedEntries.map(({ index }) => index));

  return {
    digest: {
      recipient,
      notifications: selectedEntries.map(({ notification }) => notification),
    },
    notifications: notifications.map((notification, index) =>
      selectedIndexes.has(index)
        ? cloneNotification(notification, true)
        : cloneNotification(notification, notification?.sent === true),
    ),
=======
const QUEUED_STATUS = "queued";
const SENT_STATUS = "sent";

function normalizeRecipient(value) {
  return String(value ?? "").trim().toLowerCase();
}

function normalizeId(value) {
  return String(value ?? "").trim();
}

function makeRecipientScopedId(recipient, id) {
  return `${normalizeRecipient(recipient)}\u0000${normalizeId(id)}`;
}

function isQueued(notification) {
  return String(notification?.status ?? QUEUED_STATUS).toLowerCase() === QUEUED_STATUS;
}

export function buildRecipientDigest(notifications) {
  const digestByRecipient = new Map();
  for (const notification of notifications ?? []) {
    if (!isQueued(notification)) {
      continue;
    }
    const recipient = normalizeRecipient(notification?.recipient);
    const id = normalizeId(notification?.id);
    if (!recipient || !id) {
      continue;
    }
    const entry = {
      id,
      recipient,
      subject: String(notification?.subject ?? ""),
      body: String(notification?.body ?? ""),
      createdAt: String(notification?.createdAt ?? ""),
    };
    const bucket = digestByRecipient.get(recipient) ?? [];
    bucket.push(entry);
    digestByRecipient.set(recipient, bucket);
  }
  return Array.from(digestByRecipient.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([recipient, entries]) => ({ recipient, entries }));
}

export function flushRecipientDigest(notifications, recipient, options = {}) {
  const recipientKey = normalizeRecipient(recipient);
  const sentAt = String(options.sentAt ?? new Date().toISOString());
  const digest = buildRecipientDigest(notifications).find((item) => item.recipient === recipientKey);
  if (!recipientKey || !digest) {
    return { recipient: recipientKey, sent: 0, sentIds: [] };
  }

  const sentKeys = new Set(
    digest.entries.map((entry) => makeRecipientScopedId(entry.recipient, entry.id)),
  );

  let sentCount = 0;
  for (const notification of notifications ?? []) {
    if (!isQueued(notification)) {
      continue;
    }
    const key = makeRecipientScopedId(notification?.recipient, notification?.id);
    if (!sentKeys.has(key)) {
      continue;
    }
    notification.status = SENT_STATUS;
    notification.sentAt = sentAt;
    sentCount += 1;
  }

  return {
    recipient: recipientKey,
    sent: sentCount,
    sentIds: digest.entries.map((entry) => entry.id),
>>>>>>> 9bc5021 (fix: harden runtime connectors and normalize prosper chat frontend validation)
  };
}

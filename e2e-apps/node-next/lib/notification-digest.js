const QUEUED_STATUS = "queued";
const SENT_STATUS = "sent";

function normalizeRecipient(value) {
  return String(value ?? "").trim().toLowerCase();
}

function normalizeId(value) {
  return String(value ?? "").trim();
}

function normalizeMaxItems(maxItems, totalItems) {
  if (!Number.isFinite(maxItems) || maxItems <= 0) {
    return totalItems;
  }

  return Math.min(Math.floor(maxItems), totalItems);
}

function parseCreatedAt(value) {
  const createdAt = String(value ?? "");
  const timestamp = Date.parse(createdAt);
  return Number.isFinite(timestamp) ? timestamp : 0;
}

function compareDigestEntries(left, right) {
  const leftTime = parseCreatedAt(left.createdAt);
  const rightTime = parseCreatedAt(right.createdAt);

  if (leftTime !== rightTime) {
    return leftTime - rightTime;
  }

  return left.id.localeCompare(right.id);
}

function isQueued(notification) {
  if (notification && "status" in notification) {
    return String(notification.status ?? "").toLowerCase() === QUEUED_STATUS;
  }

  return notification?.sent !== true;
}

function toDigestEntry(notification) {
  return {
    id: normalizeId(notification?.id),
    recipient: normalizeRecipient(notification?.recipient),
    subject: String(notification?.subject ?? notification?.title ?? ""),
    body: String(notification?.body ?? notification?.message ?? ""),
    createdAt: String(notification?.createdAt ?? ""),
  };
}

function toNotificationSnapshot(notification) {
  if (notification && "status" in notification) {
    return {
      ...notification,
      sent: String(notification.status ?? "").toLowerCase() === SENT_STATUS,
    };
  }

  return {
    ...notification,
    sent: notification?.sent === true,
  };
}

export function buildRecipientDigest(notifications) {
  const digestByRecipient = new Map();

  for (const notification of notifications ?? []) {
    if (!isQueued(notification)) {
      continue;
    }

    const entry = toDigestEntry(notification);
    if (!entry.recipient || !entry.id) {
      continue;
    }

    const bucket = digestByRecipient.get(entry.recipient) ?? [];
    bucket.push(entry);
    digestByRecipient.set(entry.recipient, bucket);
  }

  for (const entries of digestByRecipient.values()) {
    entries.sort(compareDigestEntries);
  }

  return Array.from(digestByRecipient.entries())
    .sort((left, right) => left[0].localeCompare(right[0]))
    .map(([recipient, entries]) => ({ recipient, entries }));
}

export function flushRecipientDigest(notifications, recipient, options = {}) {
  const recipientKey = normalizeRecipient(recipient);
  const queuedEntries = (notifications ?? [])
    .map((notification, index) => ({
      notification,
      index,
      entry: toDigestEntry(notification),
    }))
    .filter(
      ({ entry, notification }) => entry.recipient === recipientKey && isQueued(notification),
    )
    .sort((left, right) => compareDigestEntries(left.entry, right.entry));

  const maxItems = normalizeMaxItems(options.maxItems, queuedEntries.length);
  const selectedEntries = queuedEntries.slice(0, maxItems);
  const selectedIndexes = new Set(selectedEntries.map(({ index }) => index));
  const sentAt = String(options.sentAt ?? new Date().toISOString());

  for (const { notification, index } of queuedEntries) {
    if (!selectedIndexes.has(index)) {
      continue;
    }

    notification.sent = true;
    if ("status" in notification) {
      notification.status = SENT_STATUS;
      notification.sentAt = sentAt;
    }
  }

  return {
    digest: {
      recipient: recipientKey,
      notifications: selectedEntries.map(({ notification }) => notification),
    },
    notifications: (notifications ?? []).map(toNotificationSnapshot),
    recipient: recipientKey,
    sent: selectedEntries.length,
    sentIds: selectedEntries.map(({ notification }) => normalizeId(notification?.id)),
  };
}

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
  };
}

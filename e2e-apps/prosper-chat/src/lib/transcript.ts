export interface TranscriptMessage {
  role: "user" | "bot";
  content: string;
}

interface TranscriptCandidate {
  role?: unknown;
  content?: unknown;
  text?: unknown;
}

function isTranscriptCandidate(value: unknown): value is TranscriptCandidate {
  return typeof value === "object" && value !== null;
}

function normalizeRole(role: unknown): TranscriptMessage["role"] | null {
  if (typeof role !== "string") {
    return null;
  }

  const normalizedRole = role.trim().toLowerCase();

  if (normalizedRole === "user") {
    return "user";
  }

  if (normalizedRole === "assistant" || normalizedRole === "bot") {
    return "bot";
  }

  return null;
}

function normalizeContent(value: TranscriptCandidate): string | null {
  const rawContent = typeof value.content === "string"
    ? value.content
    : typeof value.text === "string"
      ? value.text
      : null;

  if (rawContent === null) {
    return null;
  }

  const content = rawContent.trim();
  return content.length > 0 ? content : null;
}

export function normalizeTranscriptMessages(value: unknown): TranscriptMessage[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.flatMap((entry) => {
    if (!isTranscriptCandidate(entry)) {
      return [];
    }

    const role = normalizeRole(entry.role);
    const content = normalizeContent(entry);
    if (role === null || content === null) {
      return [];
    }

    return [{ role, content }];
  });
}

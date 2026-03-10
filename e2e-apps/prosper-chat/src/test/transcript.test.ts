import { describe, expect, it } from "vitest";

import { normalizeTranscriptMessages } from "@/lib/transcript";

describe("normalizeTranscriptMessages", () => {
  it("normalizes user, assistant, and bot entries for transcript rendering", () => {
    expect(
      normalizeTranscriptMessages([
        { role: "user", content: "I need an appointment" },
        { role: "assistant", content: "I can help with that" },
        { role: "bot", content: "What day works for you?" },
      ]),
    ).toEqual([
      {
        role: "user",
        content: "I need an appointment",
      },
      {
        role: "bot",
        content: "I can help with that",
      },
      {
        role: "bot",
        content: "What day works for you?",
      },
    ]);
  });

  it("filters invalid transcript entries and trims content", () => {
    expect(
      normalizeTranscriptMessages([
        null,
        { role: "user", content: "   " },
        { role: "assistant", content: "  Follow-up details  " },
        { role: "moderator", content: "Status update" },
        { content: "missing role" },
      ]),
    ).toEqual([
      {
        role: "bot",
        content: "Follow-up details",
      },
    ]);
  });

  it("returns an empty list for non-array transcript payloads", () => {
    expect(normalizeTranscriptMessages({ role: "user", content: "hello" })).toEqual([]);
  });
});

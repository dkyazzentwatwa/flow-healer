import { describe, expect, it } from "vitest";
import type { Json } from "@/integrations/supabase/types";
import { normalizeTranscriptMessages } from "@/lib/transcript";

describe("normalizeTranscriptMessages", () => {
  it("normalizes user, assistant, and bot entries for transcript rendering", () => {
    const transcript = [
      { role: "user", content: "I need an appointment" },
      { role: "assistant", content: "I can help with that" },
      { role: "bot", content: "What day works for you?" },
    ] satisfies Json;

    expect(normalizeTranscriptMessages(transcript)).toEqual([
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

  it("normalizes assistant aliases and widget-style text payloads", () => {
    expect(
      normalizeTranscriptMessages([
        { role: " Assistant ", text: "  Thanks for reaching out  " },
        { role: " BOT ", content: " We can help " },
      ]),
    ).toEqual([
      {
        role: "bot",
        content: "Thanks for reaching out",
      },
      {
        role: "bot",
        content: "We can help",
      },
    ]);
  });

  it("returns an empty list for non-array transcript payloads", () => {
    expect(normalizeTranscriptMessages({ role: "user", content: "hello" } as Json)).toEqual([]);
    expect(normalizeTranscriptMessages(null)).toEqual([]);
  });
});

import { describe, expect, it } from "vitest";

import {
  createInitialWidgetState,
  hydrateWidgetState,
  parseWidgetState,
} from "@/contexts/widget-state";

describe("widget state hydration", () => {
  it("builds a fresh widget state from the current greeting", () => {
    const state = createInitialWidgetState({
      embedded: true,
      greeting: "Welcome back to Prosper Chat!",
    });

    expect(state.open).toBe(true);
    expect(state.step).toBe("intent");
    expect(state.messages).toEqual([
      { id: "1", role: "bot", text: "Welcome back to Prosper Chat!" },
    ]);
    expect(state.availableSlots).toEqual([]);
    expect(state.bookingResult).toBeNull();
  });

  it("hydrates valid persisted widget fields and ignores invalid values", () => {
    const baseState = createInitialWidgetState({
      embedded: false,
      greeting: "Hello from Prosper Chat",
    });

    const state = hydrateWidgetState(
      {
        open: true,
        step: "booking-form",
        messages: [
          { id: "1", role: "bot", text: "Older greeting" },
          { id: "2", role: "user", text: "Need an appointment" },
          { id: 3, role: "bot", text: "invalid id" },
          null,
        ],
        input: 42,
        selectedServiceId: "svc_123",
        selectedDate: "2026-03-10",
        availableSlots: ["09:00", 1300, "13:30"],
        selectedSlot: "13:30",
        bookingName: "Taylor",
        bookingEmail: "taylor@example.com",
        bookingPhone: "555-0100",
        bookingResult: {
          service_name: "Consultation",
          start_time: "2026-03-10T13:30:00.000Z",
        },
      },
      baseState,
    );

    expect(state.open).toBe(true);
    expect(state.step).toBe("booking-form");
    expect(state.input).toBe("");
    expect(state.selectedServiceId).toBe("svc_123");
    expect(state.selectedDate).toBe("2026-03-10");
    expect(state.availableSlots).toEqual(["09:00", "13:30"]);
    expect(state.selectedSlot).toBe("13:30");
    expect(state.bookingName).toBe("Taylor");
    expect(state.bookingEmail).toBe("taylor@example.com");
    expect(state.bookingPhone).toBe("555-0100");
    expect(state.bookingResult).toEqual({
      service_name: "Consultation",
      start_time: "2026-03-10T13:30:00.000Z",
    });
    expect(state.messages).toEqual([
      { id: "1", role: "bot", text: "Hello from Prosper Chat" },
      { id: "2", role: "user", text: "Need an appointment" },
    ]);
  });

  it("falls back to the base state when persisted payloads are malformed", () => {
    const baseState = createInitialWidgetState({
      embedded: false,
      greeting: "Fresh greeting",
    });

    expect(parseWidgetState("{not valid json", baseState)).toEqual(baseState);
    expect(parseWidgetState(null, baseState)).toEqual(baseState);
    expect(parseWidgetState("[]", baseState)).toEqual(baseState);
  });
});

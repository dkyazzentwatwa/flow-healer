export type WidgetStep =
  | "intent"
  | "booking-service"
  | "booking-date"
  | "booking-slots"
  | "booking-form"
  | "booking-confirm"
  | "booking-calendly"
  | "faq-list"
  | "contact-options"
  | "conversation";

export interface WidgetMessage {
  id: string;
  role: "bot" | "user";
  text: string;
}

export interface WidgetBookingResult {
  service_name: string;
  start_time: string;
}

export interface WidgetState {
  open: boolean;
  step: WidgetStep;
  messages: WidgetMessage[];
  input: string;
  selectedServiceId: string | null;
  selectedDate: string;
  availableSlots: string[];
  selectedSlot: string;
  bookingName: string;
  bookingEmail: string;
  bookingPhone: string;
  bookingResult: WidgetBookingResult | null;
}

const WIDGET_STEPS: WidgetStep[] = [
  "intent",
  "booking-service",
  "booking-date",
  "booking-slots",
  "booking-form",
  "booking-confirm",
  "booking-calendly",
  "faq-list",
  "contact-options",
  "conversation",
];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isWidgetStep(value: unknown): value is WidgetStep {
  return typeof value === "string" && WIDGET_STEPS.includes(value as WidgetStep);
}

function isWidgetMessage(value: unknown): value is WidgetMessage {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    (value.role === "bot" || value.role === "user") &&
    typeof value.text === "string"
  );
}

function sanitizeMessages(
  value: unknown,
  greetingMessage: WidgetMessage,
  fallbackMessages: WidgetMessage[],
): WidgetMessage[] {
  if (!Array.isArray(value)) {
    return fallbackMessages;
  }

  const messages = value.filter(isWidgetMessage);
  if (messages.length === 0) {
    return fallbackMessages;
  }

  return messages.map((message, index) => (index === 0 ? greetingMessage : message));
}

function sanitizeStringArray(value: unknown, fallback: string[]): string[] {
  if (!Array.isArray(value)) {
    return fallback;
  }

  return value.filter((entry): entry is string => typeof entry === "string");
}

function sanitizeBookingResult(value: unknown): WidgetBookingResult | null {
  if (
    isRecord(value) &&
    typeof value.service_name === "string" &&
    typeof value.start_time === "string"
  ) {
    return {
      service_name: value.service_name,
      start_time: value.start_time,
    };
  }

  return null;
}

export function createInitialWidgetState({
  embedded = false,
  greeting,
}: {
  embedded?: boolean;
  greeting: string;
}): WidgetState {
  return {
    open: embedded,
    step: "intent",
    messages: [{ id: "1", role: "bot", text: greeting }],
    input: "",
    selectedServiceId: null,
    selectedDate: "",
    availableSlots: [],
    selectedSlot: "",
    bookingName: "",
    bookingEmail: "",
    bookingPhone: "",
    bookingResult: null,
  };
}

export function hydrateWidgetState(value: unknown, baseState: WidgetState): WidgetState {
  if (!isRecord(value)) {
    return baseState;
  }

  const greetingMessage = baseState.messages[0] ?? { id: "1", role: "bot" as const, text: "" };

  return {
    open: typeof value.open === "boolean" ? value.open : baseState.open,
    step: isWidgetStep(value.step) ? value.step : baseState.step,
    messages: sanitizeMessages(value.messages, greetingMessage, baseState.messages),
    input: typeof value.input === "string" ? value.input : baseState.input,
    selectedServiceId:
      typeof value.selectedServiceId === "string" || value.selectedServiceId === null
        ? value.selectedServiceId
        : baseState.selectedServiceId,
    selectedDate: typeof value.selectedDate === "string" ? value.selectedDate : baseState.selectedDate,
    availableSlots: sanitizeStringArray(value.availableSlots, baseState.availableSlots),
    selectedSlot: typeof value.selectedSlot === "string" ? value.selectedSlot : baseState.selectedSlot,
    bookingName: typeof value.bookingName === "string" ? value.bookingName : baseState.bookingName,
    bookingEmail: typeof value.bookingEmail === "string" ? value.bookingEmail : baseState.bookingEmail,
    bookingPhone: typeof value.bookingPhone === "string" ? value.bookingPhone : baseState.bookingPhone,
    bookingResult: sanitizeBookingResult(value.bookingResult) ?? baseState.bookingResult,
  };
}

export function parseWidgetState(rawValue: string | null, baseState: WidgetState): WidgetState {
  if (!rawValue) {
    return baseState;
  }

  try {
    const parsed = JSON.parse(rawValue);
    return hydrateWidgetState(parsed, baseState);
  } catch {
    return baseState;
  }
}

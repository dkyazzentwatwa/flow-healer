import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

const originalConsoleError = console.error;
const originalConsoleWarn = console.warn;

vi.spyOn(console, "error").mockImplementation((...args: unknown[]) => {
  if (args.some((arg) => typeof arg === "string" && arg.includes("The width(-1) and height(-1) of chart"))) {
    return;
  }
  originalConsoleError(...(args as Parameters<typeof console.error>));
});

vi.spyOn(console, "warn").mockImplementation((...args: unknown[]) => {
  if (args.some((arg) => typeof arg === "string" && arg.includes("The width(-1) and height(-1) of chart"))) {
    return;
  }
  originalConsoleWarn(...(args as Parameters<typeof console.warn>));
});

import { describe, expect, it } from "vitest";

import { cn, mergeClasses } from "@/lib/utils";

describe("mergeClasses", () => {
  it("keeps the last conflicting utility so wrapper overrides stay deterministic", () => {
    expect(
      mergeClasses(
        "rounded-md border-slate-200 bg-white px-3 py-2 text-sm border-emerald-500 px-6 text-base",
      ),
    ).toBe("rounded-md bg-white py-2 border-emerald-500 px-6 text-base");
  });
});

describe("cn", () => {
  it("merges class values and ignores falsy inputs before resolving conflicts", () => {
    expect(
      cn(
        "flex items-center px-2 text-sm",
        null,
        undefined,
        ["px-4", { hidden: false, "text-base": true, "justify-between": true }],
      ),
    ).toBe("flex items-center px-4 text-base justify-between");
  });
});

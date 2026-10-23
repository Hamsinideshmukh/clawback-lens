import { describe, expect, it } from "vitest";

import { humanize, money, percent, timeLeft } from "@/lib/format";

describe("format", () => {
  it("humanizes evidence keys", () => {
    expect(humanize("signed_delivery_receipt")).toBe("signed delivery receipt");
    expect(humanize("_transactionType")).toBe("transactionType");
  });

  it("formats confidence as a percentage", () => {
    expect(percent(0.934)).toBe("93%");
    expect(percent(null)).toBe("—");
  });

  it("formats money in the case currency", () => {
    expect(money("249.99", "USD")).toBe("$249.99");
  });

  it("describes time to a deadline", () => {
    const now = new Date("2026-10-01T00:00:00Z");
    expect(timeLeft("2026-10-04T05:00:00Z", now)).toBe("3d 5h left");
    expect(timeLeft("2026-10-01T07:30:00Z", now)).toBe("7h left");
    expect(timeLeft("2026-09-30T00:00:00Z", now)).toBe("overdue");
  });
});

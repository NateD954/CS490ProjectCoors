import { describe, expect, it } from "vitest";
import { formatDate, formatSource } from "./format";

describe("formatSource", () => {
  it("drops the protocol and www but keeps the path", () => {
    expect(formatSource("https://www.google.com/maps/place/Cafe")).toBe("google.com/maps/place/Cafe");
  });

  it("shows just the host when there is no path", () => {
    expect(formatSource("https://example.com/")).toBe("example.com");
  });

  it("shortens long links to the limit and ends with an ellipsis", () => {
    const text = formatSource(`https://www.google.com/maps/place/${"a".repeat(100)}`);
    expect(text).toHaveLength(48);
    expect(text.endsWith("…")).toBe(true);
  });

  it("uses a custom limit", () => {
    expect(formatSource(`https://www.google.com/maps/place/${"a".repeat(100)}`, 20)).toHaveLength(20);
  });

  it("returns text that is not a link unchanged, and shortens it when long", () => {
    expect(formatSource("not a url")).toBe("not a url");
    expect(formatSource("x".repeat(100))).toHaveLength(48);
  });
});

describe("formatDate", () => {
  it("formats a timestamp in the viewer's locale", () => {
    const iso = "2026-10-31T12:00:00Z";
    const text = formatDate(iso);
    expect(text).toBe(new Date(iso).toLocaleDateString());
    expect(text === "Invalid Date").toBe(false);
  });
});

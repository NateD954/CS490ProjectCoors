// Optional unit tests. Run with: npm i -D vitest  then  npx vitest run
import { describe, expect, it } from "vitest";
import { hasErrors, validateTargetInput } from "./validation";

const goodUrl =
  "https://www.google.com/maps/place/Sample+Coffee/data=!4m7!3m6!1s0x89c25a2b1c1d3f3b:0x1a2b3c4d5e6f7a8b!8m2";

describe("validateTargetInput", () => {
  it("rejects a missing name", () => {
    expect(validateTargetInput({ name: "  ", sourceUrl: goodUrl }).name).toBeDefined();
  });
  it("rejects missing source information", () => {
    expect(validateTargetInput({ name: "Cafe", sourceUrl: "" }).sourceUrl).toBeDefined();
  });
  it("rejects a malformed source", () => {
    expect(validateTargetInput({ name: "Cafe", sourceUrl: "not a url" }).sourceUrl).toBeDefined();
  });
  it("rejects a link that is not from the team's platform", () => {
    expect(validateTargetInput({ name: "Cafe", sourceUrl: "https://example.com/x" }).sourceUrl).toBeDefined();
  });
  it("rejects a Google link the scraper cannot use (no place id)", () => {
    expect(
      validateTargetInput({ name: "Cafe", sourceUrl: "https://www.google.com/maps/place/Sample+Coffee" }).sourceUrl
    ).toBeDefined();
  });
  it("accepts valid input", () => {
    expect(hasErrors(validateTargetInput({ name: "Cafe", sourceUrl: goodUrl }))).toBe(false);
  });
});

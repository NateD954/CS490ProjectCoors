// Optional unit tests. Run with: npm i -D vitest  then  npx vitest run
import { describe, expect, it } from "vitest";
import { hasErrors, validateTargetInput } from "./validation";

const goodUrl = "https://www.google.com/maps/place/Sample+Coffee";

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
  it("accepts valid input", () => {
    expect(hasErrors(validateTargetInput({ name: "Cafe", sourceUrl: goodUrl }))).toBe(false);
  });
});

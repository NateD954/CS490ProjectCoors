import { describe, expect, it } from "vitest";
import { MAX_NAME_LENGTH } from "./config";
import { hasErrors, validateTargetInput } from "./validation";

const PLACE_ID = "0x89c25a2b1c1d3f3b:0x1a2b3c4d5e6f7a8b";
const GOOD_URL = `https://www.google.com/maps/place/Sample+Coffee/data=!4m7!3m6!1s${PLACE_ID}!8m2`;
const valid = { name: "Sample Coffee", sourceUrl: GOOD_URL };

describe("validateTargetInput: name", () => {
  it("rejects an empty name", () => {
    expect(validateTargetInput({ ...valid, name: "" }).name).toBeDefined();
  });

  it("rejects a name that is only spaces", () => {
    expect(validateTargetInput({ ...valid, name: "    " }).name).toBeDefined();
  });

  it("rejects a name that is too long", () => {
    const tooLong = "a".repeat(MAX_NAME_LENGTH + 1);
    expect(validateTargetInput({ ...valid, name: tooLong }).name).toBeDefined();
  });

  it("accepts a name exactly at the limit", () => {
    const atLimit = "a".repeat(MAX_NAME_LENGTH);
    expect(validateTargetInput({ ...valid, name: atLimit }).name).toBeUndefined();
  });
});

describe("validateTargetInput: link", () => {
  it("rejects a missing link", () => {
    expect(validateTargetInput({ ...valid, sourceUrl: "" }).sourceUrl).toBeDefined();
  });

  it("rejects a link that is only spaces", () => {
    expect(validateTargetInput({ ...valid, sourceUrl: "   " }).sourceUrl).toBeDefined();
  });

  it.each([["not a url"], [`ftp://www.google.com/maps/${PLACE_ID}`], ["javascript:alert(1)"]])(
    "rejects a malformed or non-web link: %s",
    (bad) => {
      expect(validateTargetInput({ ...valid, sourceUrl: bad }).sourceUrl).toBeDefined();
    }
  );

  it.each([
    [`https://evil.com/?x=${PLACE_ID}`],
    [`https://www.amazon.com/dp/B000/${PLACE_ID}`],
    [`https://google.com.evil.com/maps/${PLACE_ID}`],
    [`https://notgoogle.com/maps/${PLACE_ID}`],
  ])("rejects a link that is not really Google, even with a place id: %s", (bad) => {
    expect(validateTargetInput({ ...valid, sourceUrl: bad }).sourceUrl).toBeDefined();
  });

  it("rejects a Google link that has no place id, and says what to do", () => {
    const errors = validateTargetInput({ ...valid, sourceUrl: "https://www.google.com/maps/place/Sample+Coffee" });
    expect(errors.sourceUrl).toContain("full");
  });

  it("accepts Google subdomains and the bare domain", () => {
    expect(hasErrors(validateTargetInput({ ...valid, sourceUrl: `https://maps.google.com/maps/${PLACE_ID}` }))).toBe(false);
    expect(hasErrors(validateTargetInput({ ...valid, sourceUrl: `https://google.com/maps/place/x/data=!1s${PLACE_ID}` }))).toBe(false);
  });
});

describe("validateTargetInput: overall", () => {
  it("accepts valid input", () => {
    expect(hasErrors(validateTargetInput(valid))).toBe(false);
  });

  it("ignores spaces around the name and the link", () => {
    expect(hasErrors(validateTargetInput({ name: "  Sample Coffee  ", sourceUrl: `  ${GOOD_URL}  ` }))).toBe(false);
  });

  it("reports the name and the link problems together", () => {
    const errors = validateTargetInput({ name: "", sourceUrl: "" });
    expect(errors.name).toBeDefined();
    expect(errors.sourceUrl).toBeDefined();
  });
});

import { describe, expect, it } from "vitest";
import { suggestNameFromUrl } from "./suggest-name";
import { validateTargetInput } from "./validation";

const ID = "data=!4m7!3m6!1s0x89c2fa2bfb0d27d5:0xcceef158b20fbf10!8m2";

// S3-001: the form suggests a name from the link, and unusable names are rejected.
describe("suggestNameFromUrl", () => {
  it("uses the place name from a Google Maps link", () => {
    expect(suggestNameFromUrl(`https://www.google.com/maps/place/Chipotle+Mexican+Grill/${ID}`)).toBe("Chipotle Mexican Grill");
  });

  it("decodes percent-encoded characters", () => {
    expect(suggestNameFromUrl(`https://www.google.com/maps/place/Caf%C3%A9+M%C3%BCnch/${ID}`)).toBe("Café Münch");
  });

  it("returns nothing when the link has no place name", () => {
    expect(suggestNameFromUrl("https://www.google.com/maps")).toBe("");
    expect(suggestNameFromUrl("https://www.google.com/maps/search/pizza")).toBe("");
  });

  it("returns nothing when the place segment is only coordinates", () => {
    expect(suggestNameFromUrl("https://www.google.com/maps/place/40.8911,-74.0123/")).toBe("");
  });

  it("returns nothing for text that is not a link or has a broken encoding", () => {
    expect(suggestNameFromUrl("")).toBe("");
    expect(suggestNameFromUrl("not a url")).toBe("");
    expect(suggestNameFromUrl("https://www.google.com/maps/place/100%/")).toBe("");
  });

  it("returns nothing when the suggested name would be too long", () => {
    expect(suggestNameFromUrl(`https://www.google.com/maps/place/${"a".repeat(121)}/${ID}`)).toBe("");
  });
});

describe("validateTargetInput name rule", () => {
  const url = `https://www.google.com/maps/place/Sample/${ID}`;

  it("rejects a name with no letter or number", () => {
    expect(validateTargetInput({ name: "---", sourceUrl: url }).name).toBe("Use at least one letter or number in the name.");
  });

  it("accepts names with letters from other languages and numbers", () => {
    expect(validateTargetInput({ name: "カフェ 2", sourceUrl: url }).name).toBeUndefined();
    expect(validateTargetInput({ name: "7", sourceUrl: url }).name).toBeUndefined();
  });
});

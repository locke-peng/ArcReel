import { describe, expect, it } from "vitest";
import { parseReferenceImageLabels } from "../h3-generation-options";

describe("parseReferenceImageLabels", () => {
  it("keeps one trimmed label per non-empty line", () => {
    expect(parseReferenceImageLabels(" 沈家新房 \n\n姜采苓\r\n 沈延/被附身 ")).toEqual([
      "沈家新房",
      "姜采苓",
      "沈延/被附身",
    ]);
  });

  it("returns undefined for blank input", () => {
    expect(parseReferenceImageLabels(" \n \r\n")).toBeUndefined();
  });

  it("does not split commas inside an asset name", () => {
    expect(parseReferenceImageLabels("客栈, 夜景\n姜采苓")).toEqual(["客栈, 夜景", "姜采苓"]);
  });
});

/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import { errorText, formatValue, lockText, sameValue, slugKey, visibleSorted } from "../helpers";
import { choice, prop } from "./fixtures";

describe("formatValue", () => {
  it("trims numbers and names booleans", () => {
    expect(formatValue(prop({ type: "number" }), 2.5)).toBe("2.5");
    expect(formatValue(prop({ type: "number" }), 3)).toBe("3");
    expect(formatValue(prop({ type: "boolean" }), false)).toBe("No");
    expect(formatValue(prop({ type: "boolean" }), true)).toBe("Yes");
  });

  it("shows option labels, falling back to the id", () => {
    expect(formatValue(choice({ multiple: true }), ["a", "b"])).toBe("Alpha, Beta");
    expect(formatValue(choice(), "gone")).toBe("gone");
  });

  it("formats dates and members", () => {
    expect(formatValue(prop({ type: "date" }), "2026-11-09")).toBe("Nov 9, 2026");
    expect(formatValue(prop({ type: "member", multiple: true }), ["u1", "u2"], (id) => id.toUpperCase())).toBe(
      "U1, U2"
    );
  });

  it("is null when empty", () => {
    expect(formatValue(prop(), null)).toBeNull();
    expect(formatValue(prop(), "")).toBeNull();
    expect(formatValue(choice({ multiple: true }), [])).toBeNull();
  });
});

describe("visibleSorted", () => {
  it("drops hidden properties and orders by sort_order", () => {
    const [a, b, c] = [prop({ sort_order: 3 }), prop({ sort_order: 1 }), prop({ visible: false, sort_order: 2 })];
    expect(visibleSorted([a, b, c])).toEqual([b, a]);
  });
});

describe("slugKey", () => {
  it("makes a key that starts with a letter", () => {
    expect(slugKey("Story points")).toBe("story_points");
    expect(slugKey("  Customer / Org ")).toBe("customer_org");
    expect(slugKey("1st")).toBe("p_1st");
    expect(slugKey("x".repeat(80))).toHaveLength(64);
  });
});

describe("sameValue", () => {
  it("treats empty text as cleared and compares lists in order", () => {
    expect(sameValue("", null)).toBe(true);
    expect(sameValue(["a", "b"], ["a", "b"])).toBe(true);
    expect(sameValue(["a", "b"], ["b", "a"])).toBe(false);
    expect(sameValue([], null)).toBe(true);
    expect(sameValue(0, null)).toBe(false);
    expect(sameValue(false, null)).toBe(false);
  });
});

describe("lockText and errorText", () => {
  it("says who can change it", () => {
    expect(lockText(20)).toBe("Only admins can change this");
    expect(lockText(15)).toBe("Only members and admins can change this");
  });

  it("reads the server's reason", () => {
    expect(errorText({ custom_fields: { repo: "expects one of…" } }, "repo")).toBe("expects one of…");
    expect(errorText({ error: "Only project admins can change properties" })).toBe(
      "Only project admins can change properties"
    );
    expect(errorText({ key: ["key 'x' is already used"] })).toBe("key 'x' is already used");
    expect(errorText(undefined)).toBe("Couldn't save the change");
  });
});

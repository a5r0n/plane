/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import { currentStep, fromLocalInput, moveStep, stepTone, summarize, toLocalInput } from "../helpers";
import { FUTURE, PAST, step } from "./fixtures";

describe("currentStep", () => {
  it("is the first pending or failed step, so a failed step holds the path", () => {
    const steps = [step({ status: "done" }), step({ status: "failed" }), step()];
    expect(currentStep(steps)).toBe(steps[1]);
    expect(currentStep([step({ status: "done" }), step({ status: "skipped" })])).toBeUndefined();
  });
});

describe("stepTone", () => {
  const mine = { ...step({ actor: "me" }) };
  it("is amber on the viewer's turn and neutral for anyone else's", () => {
    expect(stepTone(mine, "me")).toBe("turn");
    expect(stepTone(mine, "you")).toBe("neutral");
  });
  it("is red when failed, even on the viewer's turn", () => {
    expect(stepTone({ ...mine, status: "failed" }, "me")).toBe("failed");
  });
  it("is grey while not_before is in the future, amber once it passes", () => {
    expect(stepTone({ ...mine, not_before: FUTURE }, "me")).toBe("waiting");
    expect(stepTone({ ...mine, not_before: PAST }, "me")).toBe("turn");
  });
});

describe("summarize", () => {
  it("counts done and skipped as done and names the current step", () => {
    const steps = [step({ status: "done" }), step({ status: "skipped" }), step({ title: "ship", actor: "a" })];
    expect(summarize(steps)).toMatchObject({ done: 2, total: 3, current: { title: "ship", actor: "a" } });
  });
  it("is null without steps", () => {
    expect(summarize([])).toBeNull();
  });
});

describe("moveStep", () => {
  it("swaps with the neighbour and stays put at the edges", () => {
    const [a, b, c] = [step(), step(), step()];
    expect(moveStep([a, b, c], b.id, -1)).toEqual([b, a, c]);
    expect(moveStep([a, b, c], b.id, 1)).toEqual([a, c, b]);
    const same = [a, b];
    expect(moveStep(same, a.id, -1)).toBe(same);
  });
});

describe("datetime-local round trip", () => {
  it("keeps the instant", () => {
    const iso = "2026-11-08T10:30:00.000Z";
    expect(fromLocalInput(toLocalInput(iso))).toBe(iso);
    expect(fromLocalInput("")).toBeNull();
  });
});

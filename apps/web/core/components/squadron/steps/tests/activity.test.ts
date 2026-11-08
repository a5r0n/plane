/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import { describeStepActivity } from "../activity";

const json = (value: unknown) => JSON.stringify(value);

describe("describeStepActivity", () => {
  it("names added and removed steps", () => {
    expect(describeStepActivity({ verb: "created", new_value: json({ title: "build" }) })).toEqual({
      text: "added step",
      title: "build",
    });
    expect(describeStepActivity({ verb: "deleted", old_value: json({ title: "build" }) })).toMatchObject({
      text: "removed step",
      title: "build",
    });
  });

  it("reads a status change as finished or failed, with the note", () => {
    const old = json({ title: "build", status: "pending" });
    expect(
      describeStepActivity({
        verb: "updated",
        old_value: old,
        new_value: json({ title: "build", status: "failed", note: "red" }),
      })
    ).toEqual({ text: "marked failed", title: "build", note: "red" });
    expect(
      describeStepActivity({
        verb: "updated",
        old_value: old,
        new_value: json({ title: "build", status: "done", note: "" }),
      })
    ).toMatchObject({ text: "finished", title: "build" });
  });

  it("reads whole-path writes", () => {
    const path = json([{ title: "a" }, { title: "b" }]);
    expect(
      describeStepActivity({ verb: "updated", old_value: path, new_value: path, comment: "reordered the path" }).text
    ).toBe("reordered the path");
    expect(
      describeStepActivity({ verb: "updated", old_value: "[]", new_value: path, comment: "set the path (2 steps)" })
        .text
    ).toBe("replaced the path (2 steps)");
  });
});

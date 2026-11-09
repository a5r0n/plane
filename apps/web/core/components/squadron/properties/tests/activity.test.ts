/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import { describePropertyActivity } from "../activity";

describe("describePropertyActivity", () => {
  it("names set, changed and cleared", () => {
    expect(describePropertyActivity({ comment: "updated Repo", old_value: null, new_value: "plane" })).toEqual({
      verb: "set",
      name: "Repo",
      to: "plane",
    });
    expect(describePropertyActivity({ comment: "updated Points", old_value: "2", new_value: "3" })).toEqual({
      verb: "changed",
      name: "Points",
      from: "2",
      to: "3",
    });
    expect(describePropertyActivity({ comment: "updated Owner", old_value: "Ann", new_value: null })).toEqual({
      verb: "cleared",
      name: "Owner",
      from: "Ann",
    });
  });
});

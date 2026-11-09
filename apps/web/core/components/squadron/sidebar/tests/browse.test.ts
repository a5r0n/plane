/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import { isBrowsingProject } from "../browse";

describe("isBrowsingProject", () => {
  it("matches the key's project identifier, in any case", () => {
    expect(isBrowsingProject("EPD-12", "EPD")).toBe(true);
    expect(isBrowsingProject("epd-12", "EPD")).toBe(true);
  });

  it("keeps a dash inside the identifier", () => {
    expect(isBrowsingProject("MY-APP-3", "MY-APP")).toBe(true);
    expect(isBrowsingProject("MY-APP-3", "MY")).toBe(false);
  });

  it("is false for another project or no key", () => {
    expect(isBrowsingProject("EPDX-1", "EPD")).toBe(false);
    expect(isBrowsingProject("EPD", "EPD")).toBe(false);
    expect(isBrowsingProject(undefined, "EPD")).toBe(false);
    expect(isBrowsingProject("EPD-1", undefined)).toBe(false);
  });
});

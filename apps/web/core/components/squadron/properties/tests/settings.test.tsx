/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { dropOrder, midpoint } from "../helpers";
import type { TPropertiesApi } from "../service";
import { PropertiesStore } from "../store";
import type { TProperty } from "../types";
import { choice, prop } from "./fixtures";

vi.stubGlobal(
  "ResizeObserver",
  class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
);

const holder = vi.hoisted(() => ({ store: undefined as unknown }));
vi.mock("../use-properties", () => ({ useProperties: () => holder.store }));

const { PropertiesSettings } = await import("../settings/properties-settings");

afterEach(cleanup);

const show = async (defs: TProperty[]) => {
  const api = { list: vi.fn().mockResolvedValue(defs) } as unknown as TPropertiesApi;
  holder.store = new PropertiesStore(api);
  render(<PropertiesSettings workspaceSlug="acme" projectId="p1" />);
};

describe("PropertiesSettings", () => {
  it("lists properties with their key and badges", async () => {
    await show([
      prop({ name: "Customer", key: "customer", visible: false, write_role: 20 }),
      choice({ name: "Tags", key: "tags", multiple: true, write_role: 5 }),
    ]);
    expect(await screen.findByText("Customer")).toBeTruthy();
    expect(screen.getByText("customer").className).toContain("font-mono");
    expect(screen.getByText("Hidden")).toBeTruthy();
    expect(screen.getByText("Admins only")).toBeTruthy();
    expect(screen.getByText("Guests can set")).toBeTruthy();
    expect(screen.getByText("Multiple")).toBeTruthy();
  });

  it("shows the empty state", async () => {
    await show([]);
    expect(await screen.findByText("No properties yet. Add one to track your own fields on work items.")).toBeTruthy();
  });

  it("opens the create modal from Add property", async () => {
    await show([]);
    expect(screen.queryByLabelText("Key")).toBeNull();
    fireEvent.click(screen.getAllByRole("button", { name: "Add property" })[0]);
    expect(await screen.findByLabelText("Key")).toBeTruthy();
  });
});

describe("midpoint", () => {
  it("halves between neighbours and steps 1000 past an end", () => {
    expect(midpoint(1000, 2000)).toBe(1500);
    expect(midpoint(undefined, 2000)).toBe(1000);
    expect(midpoint(3000, undefined)).toBe(4000);
    expect(midpoint(undefined, undefined)).toBe(1000);
  });
});

describe("dropOrder", () => {
  const defs = [prop({ sort_order: 1000 }), prop({ sort_order: 2000 }), prop({ sort_order: 3000 })];

  it("lands between the target and its neighbour on the dropped edge", () => {
    expect(dropOrder(defs, defs[2].id, defs[1].id, "top")).toBe(1500);
    expect(dropOrder(defs, defs[0].id, defs[1].id, "bottom")).toBe(2500);
    expect(dropOrder(defs, defs[0].id, defs[2].id, "bottom")).toBe(4000);
  });

  it("is null when the drop doesn't move it", () => {
    expect(dropOrder(defs, defs[1].id, defs[1].id, "top")).toBeNull();
    expect(dropOrder(defs, defs[0].id, defs[1].id, "top")).toBeNull();
  });
});

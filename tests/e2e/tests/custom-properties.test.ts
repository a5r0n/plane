/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { beforeAll, describe, expect, inject, it } from "vitest";
import { ApiClient } from "../src/plane";

const stack = inject("stack");
const api = new ApiClient(stack.apiKey, stack.workspaceSlug);
const items = `projects/${stack.projectId}/work-items/`;
const properties = `projects/${stack.projectId}/properties/`;

type Fields = Record<string, unknown>;
type Item = { id: string; custom_fields: Fields };
type Activity = { field: string | null; old_value: string | null; new_value: string | null };

describe("custom properties on the v1 API", () => {
  let itemId: string;
  let repoId: string;
  const read = () => api.call<Item>("GET", `${items}${itemId}/`);
  const find = async (pql: string) =>
    (await api.call<{ results: Item[] }>("GET", `${items}?pql=${encodeURIComponent(pql)}`)).results.map((i) => i.id);

  beforeAll(async () => {
    const repo = await api.call<{ id: string }>("POST", properties, {
      name: "E2E repo",
      key: "e2e_repo",
      type: "choice",
      options: [{ label: "Plane" }, { label: "MCP" }],
    });
    repoId = repo.id;
    await api.call("POST", properties, { name: "E2E count", key: "e2e_count", type: "number" });
  });

  it("creates an item with values, reads them back and changes one", async () => {
    const created = await api.call<Item>("POST", items, {
      name: "Custom properties E2E",
      custom_fields: { e2e_repo: "plane", e2e_count: 2 },
    });
    itemId = created.id;
    expect(created.custom_fields).toMatchObject({ e2e_repo: "plane", e2e_count: 2 });

    const patched = await api.call<Item>("PATCH", `${items}${itemId}/`, { custom_fields: { e2e_count: 3.5 } });
    expect(patched.custom_fields).toMatchObject({ e2e_repo: "plane", e2e_count: 3.5 });
    expect((await read()).custom_fields).toMatchObject({ e2e_repo: "plane", e2e_count: 3.5 });
  });

  it("finds the item by its values with PQL", async () => {
    expect(await find('prop.e2e_repo = "plane" AND prop.e2e_count > 3')).toEqual([itemId]);
    expect(await find('prop.e2e_repo = "mcp"')).toEqual([]);
  });

  it("records each change in the item's activity", async () => {
    const { results } = await api.call<{ results: Activity[] }>("GET", `${items}${itemId}/activities/?per_page=100`);
    const rows = results.filter((row) => row.field === "custom_fields");
    expect(rows.map((row) => [row.old_value, row.new_value])).toEqual(
      expect.arrayContaining([
        [null, "Plane"],
        ["2", "3.5"],
      ])
    );
  });

  it("drops a deleted property from reads", async () => {
    await api.call("DELETE", `${properties}${repoId}/`);
    const fields = (await read()).custom_fields;
    expect(fields).not.toHaveProperty("e2e_repo");
    expect(fields).toMatchObject({ e2e_count: 3.5 });
  });
});

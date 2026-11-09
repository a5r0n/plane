/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { beforeAll, describe, expect, inject, it } from "vitest";
import { API_URL, ApiClient } from "../src/plane";

const stack = inject("stack");
const api = new ApiClient(stack.apiKey, stack.workspaceSlug);
const project = `projects/${stack.projectId}/`;

/** A POST whose status we assert, since a refusal is the answer we want. */
async function post(path: string, body: unknown): Promise<{ status: number; body: unknown }> {
  const response = await fetch(new URL(`/api/v1/workspaces/${stack.workspaceSlug}/${project}${path}`, API_URL), {
    method: "POST",
    headers: { "x-api-key": stack.apiKey, "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return { status: response.status, body: await response.json() };
}

describe("epics stay out of cycles and modules on the v1 API", () => {
  let epicId: string;
  let itemId: string;

  beforeAll(async () => {
    epicId = (await api.call<{ id: string }>("POST", `${project}epics/`, { name: "Refuse E2E epic" })).id;
    itemId = (await api.call<{ id: string }>("POST", `${project}work-items/`, { name: "Refuse E2E item" })).id;
  });

  it("refuses an epic in a cycle and still takes a work item", async () => {
    const cycle = await api.call<{ id: string }>("POST", `${project}cycles/`, { name: "Refuse E2E cycle" });
    const route = `cycles/${cycle.id}/cycle-issues/`;

    const refused = await post(route, { issues: [itemId, epicId] });
    expect(refused).toEqual({ status: 400, body: { error: "An epic can't be added to a cycle.", ids: [epicId] } });
    expect(await api.call<{ results: unknown[] }>("GET", `${project}${route}`)).toMatchObject({ results: [] });

    expect((await post(route, { issues: [itemId] })).status).toBeLessThan(300);
  });

  it("refuses an epic in a module and still takes a work item", async () => {
    const module = await api.call<{ id: string }>("POST", `${project}modules/`, { name: "Refuse E2E module" });
    const route = `modules/${module.id}/module-issues/`;

    const refused = await post(route, { issues: [epicId] });
    expect(refused).toEqual({ status: 400, body: { error: "An epic can't be added to a module.", ids: [epicId] } });

    expect((await post(route, { issues: [itemId] })).status).toBeLessThan(300);
  });
});

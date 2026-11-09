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

type Activity = { id: string; field: string | null; provenance: unknown };

// No celery worker here: comment rows come from the task, which pytest covers; step rows are written inline.
describe("work item activity on the v1 API", () => {
  let itemId: string;
  const activities = (tail = "") => `${items}${itemId}/activities/${tail}`;

  beforeAll(async () => {
    itemId = (await api.call<{ id: string }>("POST", items, { name: "Activity E2E" })).id;
    await api.call("POST", `${items}${itemId}/steps/`, { title: "build" });
    await api.call("POST", `${items}${itemId}/comments/`, { comment_html: "<p>via e2e</p>" });
  });

  it("lists rows with a provenance key and serves one by id", async () => {
    const { results } = await api.call<{ results: Activity[] }>("GET", activities("?per_page=100"));
    const step = results.find((row) => row.field === "step");
    expect(step).toBeDefined();
    expect(results.every((row) => "provenance" in row)).toBe(true);

    const one = await api.call<Activity>("GET", activities(`${step!.id}/`));
    expect([one.id, one.field, "provenance" in one]).toEqual([step!.id, "step", true]);
  });

  it("serves the same routes under the issues prefix", async () => {
    const path = `projects/${stack.projectId}/issues/${itemId}/activities/`;
    const { results } = await api.call<{ results: Activity[] }>("GET", path);
    expect(results.some((row) => row.field === "step")).toBe(true);
  });
});

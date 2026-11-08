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

type Step = { id: string; title: string; status: string; note: string; actor: string | null };
type Item = { id: string; steps: Step[]; current_step: Step | null };
type Activity = { field: string | null; verb: string; new_value: string | null };

describe("work item steps on the v1 API", () => {
  let itemId: string;
  const steps = (tail = "") => `${items}${itemId}/steps/${tail}`;
  const read = () => api.call<Item>("GET", `${items}${itemId}/?fields=steps,current_step`);

  beforeAll(async () => {
    itemId = (await api.call<{ id: string }>("POST", items, { name: "Steps E2E" })).id;
  });

  it("sets the path, finishes a step and reorders, with the current step following", async () => {
    const path = await api.call<Step[]>("POST", steps("set-path/"), {
      steps: [{ title: "build", actor: stack.userId }, { title: "test" }, { title: "ship" }],
    });
    expect(path.map((step) => step.title)).toEqual(["build", "test", "ship"]);
    expect((await read()).current_step?.title).toBe("build");

    const [build, test, ship] = path;
    const done = await api.call<Step>("PATCH", steps(`${build.id}/`), { status: "done", note: "green" });
    expect([done.status, done.note]).toEqual(["done", "green"]);
    expect((await read()).current_step?.title).toBe("test");

    await api.call<Step[]>("POST", steps("reorder/"), { step_ids: [build.id, ship.id, test.id] });
    const item = await read();
    expect(item.steps.map((step) => step.title)).toEqual(["build", "ship", "test"]);
    expect(item.current_step?.title).toBe("ship");
  });

  it("records each write as one step row in the item's activity", async () => {
    const { results } = await api.call<{ results: Activity[] }>("GET", `${items}${itemId}/activities/?per_page=100`);
    const rows = results.filter((row) => row.field === "step");
    expect(rows.map((row) => row.verb)).toEqual(["updated", "updated", "updated"]);
    const finished = JSON.parse(rows[1].new_value ?? "{}") as Step;
    expect([finished.title, finished.status]).toEqual(["build", "done"]);
  });

  it("finds the item by its current step's actor with PQL", async () => {
    const other = (await api.call<{ id: string }>("POST", items, { name: "Steps E2E queue" })).id;
    await api.call<Step>("POST", `${items}${other}/steps/`, { title: "review", actor: stack.userId });
    const pql = encodeURIComponent('stepActor = currentUser() AND title ~ "steps e2e"');
    const { results } = await api.call<{ results: { id: string }[] }>("GET", `${items}?pql=${pql}`);
    expect(results.map((item) => item.id)).toEqual([other]);
  });
});

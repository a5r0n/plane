/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, inject, it } from "vitest";
import { ApiClient } from "../src/plane";

const stack = inject("stack");
const api = new ApiClient(stack.apiKey, stack.workspaceSlug);
const items = `projects/${stack.projectId}/work-items/`;

type Ref = { project_id: string; issue_id: string };
type Relations = Record<string, Ref[]>;
type Activity = { field: string | null; verb: string };

describe("the implemented_by / implements relation on the v1 API", () => {
  it("creates from the build item, reads both sides, records activity and removes from the idea", async () => {
    const create = async (name: string) => (await api.call<{ id: string }>("POST", items, { name })).id;
    const idea = await create("Relations E2E idea");
    const build = await create("Relations E2E build");
    const relations = (id: string, tail = "") => `${items}${id}/relations/${tail}`;
    const ref = (id: string): Ref => ({ project_id: stack.projectId, issue_id: id });

    await api.call("POST", relations(build), { relation_type: "implements", issues: [idea] });

    const ideaView = await api.call<Relations>("GET", relations(idea));
    const buildView = await api.call<Relations>("GET", relations(build));
    expect(ideaView.implemented_by).toEqual([ref(build)]);
    expect(buildView.implements).toEqual([ref(idea)]);
    expect(ideaView.blocked_by).toEqual([]);

    await expect
      .poll(
        async () => {
          const { results } = await api.call<{ results: Activity[] }>(
            "GET",
            `${items}${idea}/activities/?per_page=100`
          );
          return results.some((row) => row.field === "implemented_by" && row.verb === "updated");
        },
        { timeout: 15000 }
      )
      .toBe(true);

    await api.call("POST", relations(idea, "remove/"), { related_issue: build });
    expect((await api.call<Relations>("GET", relations(build))).implements).toEqual([]);
    expect((await api.call<Relations>("GET", relations(idea))).implemented_by).toEqual([]);
  });
});

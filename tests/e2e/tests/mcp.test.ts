/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { afterAll, beforeAll, describe, expect, inject, it } from "vitest";
import { openPage } from "../src/collab";
import { McpClient } from "../src/mcp";
import type { Page } from "../src/plane";

const stack = inject("stack");

describe("the Plane MCP server against the fork", () => {
  let mcp: McpClient;
  // uvx fetches and builds the pinned server on a cold cache
  beforeAll(async () => {
    mcp = await McpClient.start(stack);
  }, 180_000);
  afterAll(() => mcp?.close());

  it("lists the project through its tools", async () => {
    const { tools } = await mcp.request<{ tools: { name: string }[] }>("tools/list");
    expect(tools.map((tool) => tool.name)).toEqual(expect.arrayContaining(["project", "page", "workitem"]));

    const listed = await mcp.tool<{ results?: { id: string }[] } | { id: string }[]>("project", { action: "list" });
    const projects = Array.isArray(listed) ? listed : (listed.results ?? []);
    expect(projects.map((project) => project.id)).toContain(stack.projectId);
  });

  it("filters work items with PQL on the server", async () => {
    const make = (name: string, priority: string) =>
      mcp.tool<{ id: string }>("workitem", { action: "create", project_id: stack.projectId, name, priority });
    const urgent = await make("PQL urgent", "urgent");
    await make("PQL low", "low");

    const listed = await mcp.tool<{ results?: { id: string }[] } | { error: string }>("workitem", {
      action: "list",
      project_id: stack.projectId,
      pql: 'priority = "urgent" AND title ~ "pql"',
    });
    expect("results" in listed ? listed.results?.map((item) => item.id) : listed).toEqual([urgent.id]);
  });

  it("creates and rewrites a page that an open editor follows", async () => {
    const created = await mcp.tool<Page>("page", {
      action: "create",
      project_id: stack.projectId,
      name: "From the MCP",
      description_html: "<p>first draft</p>",
    });
    const editor = await openPage(stack, created.id);
    try {
      expect(editor.body()).toContain("first draft");

      await mcp.tool<Page>("page", {
        action: "update",
        project_id: stack.projectId,
        page_id: created.id,
        description_html: "<p>second draft</p>",
      });
      await editor.waitFor(editor.body, (value) => value.includes("second draft"));

      const read = await mcp.tool<Page>("page", {
        action: "retrieve",
        project_id: stack.projectId,
        page_id: created.id,
      });
      expect(read.description_html).toContain("second draft");
    } finally {
      editor.close();
    }
  });
});

/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { randomBytes } from "node:crypto";
import { beforeAll, describe, expect, it } from "vitest";
import { ApiClient, BrowserSession } from "../src/plane";

// seeded by the migrator and listed in SQUADRON_READ_ONLY_USER_IDS (docker-compose-e2e.yml)
const EMAIL = "readonly@plane.local";
const PASSWORD = "Plane-e2e-correct-horse-42";

type Comment = { id: string };

describe("a read-only identity on the v1 API", () => {
  let api: ApiClient;
  let workItem: string;

  // its own workspace, set up through the web session, which the setting doesn't touch
  beforeAll(async () => {
    const user = new BrowserSession();
    const signedIn = await user.submitForm("/auth/sign-in/", { email: EMAIL, password: PASSWORD });
    const error = signedIn.searchParams.get("error_code");
    if (error) throw new Error(`sign-in failed: ${error} ${signedIn.searchParams.get("error_message")}`);

    const slug = `ro-${randomBytes(4).toString("hex")}`;
    await user.json("/api/workspaces/", { method: "POST", body: JSON.stringify({ name: slug, slug }) });
    const project = await user.json<{ id: string }>(`/api/workspaces/${slug}/projects/`, {
      method: "POST",
      body: JSON.stringify({ name: "Read only", identifier: "RO" }),
    });
    const issue = await user.json<{ id: string }>(`/api/workspaces/${slug}/projects/${project.id}/issues/`, {
      method: "POST",
      body: JSON.stringify({ name: "Untouched" }),
    });
    const { token } = await user.json<{ token: string }>("/api/users/api-tokens/", {
      method: "POST",
      body: JSON.stringify({ label: slug }),
    });
    api = new ApiClient(token, slug);
    workItem = `projects/${project.id}/work-items/${issue.id}/`;
  });

  it("reads work items and comments", async () => {
    const item = await api.call<{ name: string }>("GET", workItem);
    expect(item.name).toBe("Untouched");
    expect((await api.send("GET", `${workItem}comments/`)).status).toBe(200);
  });

  it("is refused every write, and nothing changes", async () => {
    const writes = [
      await api.send("POST", `${workItem}comments/`, { comment_html: "<p>should not land</p>" }),
      await api.send("PATCH", workItem, { name: "Changed" }),
      await api.send("DELETE", workItem),
    ];
    expect(writes.map((response) => response.status)).toEqual([403, 403, 403]);
    const bodies = await Promise.all(writes.map((response) => response.json()));
    expect(bodies).toEqual(writes.map(() => ({ detail: "This identity is read-only." })));

    expect((await api.call<{ name: string }>("GET", workItem)).name).toBe("Untouched");
    const comments = await api.call<{ results: Comment[] }>("GET", `${workItem}comments/`);
    expect(comments.results).toEqual([]);
  });
});

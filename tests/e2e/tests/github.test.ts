/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { createHmac } from "node:crypto";
import { describe, expect, it } from "vitest";
import { API_URL } from "../src/plane";

// The stack sets this secret; no celery worker runs, so the rows themselves are covered in pytest.
const SECRET = "e2e-github-secret";
const sign = (body: string, secret = SECRET) => "sha256=" + createHmac("sha256", secret).update(body).digest("hex");

async function post(event: string, body: string, signature?: string) {
  const headers: Record<string, string> = {
    "content-type": "application/json",
    "X-GitHub-Event": event,
    "X-GitHub-Delivery": crypto.randomUUID(),
  };
  if (signature !== undefined) headers["X-Hub-Signature-256"] = signature;
  return fetch(new URL("/api/github/webhook/", API_URL), { method: "POST", headers, body });
}

describe("the GitHub webhook endpoint", () => {
  const body = JSON.stringify({ action: "closed", repository: { full_name: "e2e/none" } });

  it("refuses a missing or wrong signature with 401", async () => {
    expect((await post("pull_request", body)).status).toBe(401);
    expect((await post("pull_request", body, sign(body, "wrong"))).status).toBe(401);
  });

  it("answers a signed ping with 200", async () => {
    const ping = JSON.stringify({ zen: "e2e" });
    expect((await post("ping", ping, sign(ping))).status).toBe(200);
  });

  it("queues a signed event with 202", async () => {
    expect((await post("pull_request", body, sign(body))).status).toBe(202);
  });
});

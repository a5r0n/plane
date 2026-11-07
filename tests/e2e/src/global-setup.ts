/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { randomBytes } from "node:crypto";
import type { TestProject } from "vitest/node";
import { ApiClient, BrowserSession } from "./plane";

export type Stack = {
  cookie: string;
  userId: string;
  workspaceSlug: string;
  projectId: string;
  apiKey: string;
};

declare module "vitest" {
  export interface ProvidedContext {
    stack: Stack;
  }
}

const EMAIL = "e2e@plane.local";
const PASSWORD = "Plane-e2e-correct-horse-42";

/** Sets the stack up over HTTP as a new user would; reruns against the same stack reuse the admin. */
export default async function setup(project: TestProject) {
  // an instance set up by an earlier run refuses a second admin; signing in then is enough
  await new BrowserSession().submitForm("/api/instances/admins/sign-up/", {
    email: EMAIL,
    password: PASSWORD,
    first_name: "E2E",
    company_name: "E2E",
  });
  const user = new BrowserSession();
  const signedIn = await user.submitForm("/auth/sign-in/", { email: EMAIL, password: PASSWORD });
  const error = signedIn.searchParams.get("error_code");
  if (error) throw new Error(`sign-in failed: ${error} ${signedIn.searchParams.get("error_message")}`);

  const me = await user.json<{ id: string }>("/api/users/me/");
  const slug = `e2e-${randomBytes(4).toString("hex")}`;
  await user.json("/api/workspaces/", { method: "POST", body: JSON.stringify({ name: slug, slug }) });
  const { token } = await user.json<{ token: string }>("/api/users/api-tokens/", {
    method: "POST",
    body: JSON.stringify({ label: slug }),
  });
  const project_ = await new ApiClient(token, slug).call<{ id: string }>("POST", "projects/", {
    name: "E2E",
    identifier: "E2E",
  });

  project.provide("stack", {
    cookie: user.cookieHeader,
    userId: me.id,
    workspaceSlug: slug,
    projectId: project_.id,
    apiKey: token,
  });
}

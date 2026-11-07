/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

export const API_URL = process.env.E2E_API_URL ?? "http://127.0.0.1:18000";
export const LIVE_URL = process.env.E2E_LIVE_URL ?? "http://127.0.0.1:13100";

/** A browser-like session: keeps cookies and sends the CSRF token Django asks for. */
export class BrowserSession {
  private readonly cookies = new Map<string, string>();

  get cookieHeader(): string {
    return [...this.cookies].map(([name, value]) => `${name}=${value}`).join("; ");
  }

  async request(path: string, init: RequestInit = {}): Promise<Response> {
    const headers = new Headers(init.headers);
    if (this.cookies.size) headers.set("cookie", this.cookieHeader);
    const csrf = this.cookies.get("csrftoken");
    if (csrf) headers.set("x-csrftoken", csrf);
    headers.set("referer", API_URL);
    const response = await fetch(new URL(path, API_URL), { ...init, headers, redirect: "manual" });
    for (const cookie of response.headers.getSetCookie()) {
      const [pair] = cookie.split(";");
      const at = pair.indexOf("=");
      this.cookies.set(pair.slice(0, at).trim(), pair.slice(at + 1).trim());
    }
    return response;
  }

  async json<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    if (init.body) headers.set("content-type", "application/json");
    const response = await this.request(path, { ...init, headers });
    if (!response.ok) throw new Error(`${init.method ?? "GET"} ${path}: ${response.status} ${await response.text()}`);
    return (await response.json()) as T;
  }

  /** Posts a form the way the web app does; auth views answer with a redirect carrying any error. */
  async submitForm(path: string, fields: Record<string, string>): Promise<URL> {
    if (!this.cookies.has("csrftoken")) await this.request("/auth/get-csrf-token/");
    const body = new URLSearchParams({ ...fields, csrfmiddlewaretoken: this.cookies.get("csrftoken") ?? "" });
    const response = await this.request(path, { method: "POST", body });
    const location = response.headers.get("location");
    if (response.status !== 302 || !location)
      throw new Error(`POST ${path}: ${response.status} ${await response.text()}`);
    return new URL(location, API_URL);
  }
}

/** The public v1 API, as an API-key client such as the MCP server uses it. */
export class ApiClient {
  constructor(
    private readonly apiKey: string,
    readonly workspaceSlug: string
  ) {}

  async call<T>(method: string, path: string, body?: unknown): Promise<T> {
    const response = await fetch(new URL(`/api/v1/workspaces/${this.workspaceSlug}/${path}`, API_URL), {
      method,
      headers: { "x-api-key": this.apiKey, "content-type": "application/json" },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    if (!response.ok) throw new Error(`${method} ${path}: ${response.status} ${await response.text()}`);
    return (response.status === 204 ? undefined : await response.json()) as T;
  }
}

export type Page = {
  id: string;
  name: string;
  description_html: string;
};

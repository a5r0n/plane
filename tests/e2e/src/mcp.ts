/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { createInterface } from "node:readline";
import { API_URL } from "./plane";
import type { Stack } from "./global-setup";

// bump deliberately: the suite checks the fork against this exact server
export const MCP_SERVER_REPO = "https://github.com/a5r0n/plane-mcp-server";
export const MCP_SERVER_SHA = "e5199013c763adcc4ba176c1d39bd89cea37211c";

type Pending = { resolve: (value: unknown) => void; reject: (error: Error) => void };

/** A minimal MCP client over stdio: newline-delimited JSON-RPC. */
export class McpClient {
  private nextId = 1;
  private readonly pending = new Map<number, Pending>();
  private stderr = "";

  private constructor(private readonly child: ChildProcessWithoutNullStreams) {
    createInterface({ input: child.stdout }).on("line", (line) => {
      let message: { id?: number; result?: unknown; error?: { message: string } };
      try {
        message = JSON.parse(line);
      } catch {
        return;
      }
      const waiter = message.id === undefined ? undefined : this.pending.get(message.id);
      if (!waiter) return;
      this.pending.delete(message.id!);
      if (message.error) waiter.reject(new Error(message.error.message));
      else waiter.resolve(message.result);
    });
    child.stderr.on("data", (chunk: Buffer) => (this.stderr = (this.stderr + chunk.toString()).slice(-4000)));
    child.on("exit", (code) => {
      for (const waiter of this.pending.values()) waiter.reject(new Error(`MCP server exited ${code}: ${this.stderr}`));
      this.pending.clear();
    });
  }

  static async start(stack: Stack): Promise<McpClient> {
    const command = process.env.E2E_MCP_COMMAND?.split(" ") ?? [
      "uvx",
      "--from",
      `git+${MCP_SERVER_REPO}@${MCP_SERVER_SHA}`,
      "plane-mcp-server",
    ];
    const child = spawn(command[0], command.slice(1), {
      env: {
        ...process.env,
        PLANE_BASE_URL: API_URL,
        PLANE_API_KEY: stack.apiKey,
        PLANE_WORKSPACE_SLUG: stack.workspaceSlug,
      },
    });
    const client = new McpClient(child);
    await client.request("initialize", {
      protocolVersion: "2025-06-18",
      capabilities: {},
      clientInfo: { name: "plane-e2e", version: "1" },
    });
    client.notify("notifications/initialized");
    return client;
  }

  private send(message: object) {
    this.child.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", ...message })}\n`);
  }

  notify(method: string, params?: object) {
    this.send({ method, params });
  }

  request<T>(method: string, params?: object): Promise<T> {
    const id = this.nextId++;
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, { resolve: resolve as (value: unknown) => void, reject });
      this.send({ id, method, params });
    });
  }

  /** Calls a tool and returns its structured result; a tool error throws. */
  async tool<T>(name: string, args: object): Promise<T> {
    const result = await this.request<{
      isError?: boolean;
      structuredContent?: { result?: T } & T;
      content?: { type: string; text?: string }[];
    }>("tools/call", { name, arguments: args });
    const text = result.content?.map((part) => part.text ?? "").join("") ?? "";
    if (result.isError) throw new Error(`${name} failed: ${text}`);
    const structured = result.structuredContent;
    if (structured) return (structured.result ?? structured) as T;
    return JSON.parse(text) as T;
  }

  close() {
    this.child.kill();
  }
}

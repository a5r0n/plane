/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { HocuspocusProvider, HocuspocusProviderWebsocket } from "@hocuspocus/provider";
import { WebSocket } from "ws";
import * as Y from "yjs";
import { LIVE_URL } from "./plane";
import type { Stack } from "./global-setup";

export type PageEditor = {
  doc: Y.Doc;
  /** The page body as the editor holds it. */
  body: () => string;
  /** The page title as the editor holds it. */
  title: () => string;
  /** Resolves once `read()` returns something `ready` accepts. */
  waitFor: (read: () => string, ready: (value: string) => boolean, timeoutMs?: number) => Promise<string>;
  close: () => void;
};

/** Opens a project page the way the web editor does: same URL, token and cookie. */
export async function openPage(stack: Stack, pageId: string): Promise<PageEditor> {
  const url = new URL("/live/collaboration", LIVE_URL);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.searchParams.set("documentType", "project_page");
  url.searchParams.set("projectId", stack.projectId);
  url.searchParams.set("workspaceSlug", stack.workspaceSlug);

  // the browser sends its session cookie on the upgrade; node's WebSocket needs it handed over
  const cookie = stack.cookie;
  class BrowserWebSocket extends WebSocket {
    constructor(address: string | URL, protocols?: string | string[]) {
      super(address, protocols, { headers: { cookie } });
    }
  }

  const doc = new Y.Doc();
  const socket = new HocuspocusProviderWebsocket({ url: url.toString(), WebSocketPolyfill: BrowserWebSocket });
  const provider = new HocuspocusProvider({
    websocketProvider: socket,
    name: pageId,
    document: doc,
    token: JSON.stringify({ id: stack.userId, name: "E2E", color: "#3f76ff" }),
  });

  await new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`page ${pageId} never synced`)), 15_000);
    provider.on("synced", () => {
      clearTimeout(timer);
      resolve();
    });
    provider.on("authenticationFailed", ({ reason }: { reason: string }) => {
      clearTimeout(timer);
      reject(new Error(`live refused the editor: ${reason}`));
    });
  });

  const waitFor: PageEditor["waitFor"] = (read, ready, timeoutMs = 10_000) =>
    new Promise((resolve, reject) => {
      const check = () => {
        const value = read();
        if (!ready(value)) return false;
        doc.off("update", check);
        clearTimeout(timer);
        resolve(value);
        return true;
      };
      const timer = setTimeout(() => {
        doc.off("update", check);
        reject(new Error(`timed out; last value: ${read()}`));
      }, timeoutMs);
      if (!check()) doc.on("update", check);
    });

  return {
    doc,
    body: () => doc.getXmlFragment("default").toString(),
    title: () => doc.getXmlFragment("title").toString(),
    waitFor,
    close: () => {
      provider.destroy();
      socket.destroy();
    },
  };
}

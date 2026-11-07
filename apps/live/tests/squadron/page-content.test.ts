/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { AddressInfo } from "net";
import type { Server } from "http";
import type { Hocuspocus } from "@hocuspocus/server";
import express from "express";
import * as Y from "yjs";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import {
  convertBase64StringToBinaryData,
  convertBinaryDataToBase64String,
  getAllDocumentFormatsFromDocumentEditorBinaryData,
  getBinaryDataFromDocumentEditorHTMLString,
} from "@plane/editor";
import { replacePageContent, writePageContent } from "@/squadron/page-content";

const SECRET = "test-secret";
process.env.API_BASE_URL ??= "http://localhost:8000";
process.env.LIVE_SERVER_SECRET_KEY = SECRET;

const PAGE_ID = "0b8e6b52-6a43-4c2b-9d3f-0c3d2b1a9e11";

const pageDoc = (html: string, title?: string) => {
  const doc = new Y.Doc();
  Y.applyUpdate(doc, getBinaryDataFromDocumentEditorHTMLString(html, title));
  return doc;
};
const html = (doc: Y.Doc) => getAllDocumentFormatsFromDocumentEditorBinaryData(Y.encodeStateAsUpdate(doc), true);
const fakeInstance = (loaded: Record<string, Y.Doc> = {}) =>
  ({ documents: new Map(Object.entries(loaded)), loadingDocuments: new Map() }) as unknown as Hocuspocus;

describe("replacePageContent", () => {
  it("replaces the body and keeps the title", () => {
    const doc = pageDoc("<p>old</p>", "Design");
    replacePageContent(doc, "<p>new</p>");
    const out = html(doc);
    expect(out.contentHTML).toContain("new");
    expect(out.contentHTML).not.toContain("old");
    expect(out.titleHTML).toBe("Design");
  });

  it("replaces the title when a name is given", () => {
    const doc = pageDoc("<p>old</p>", "Design");
    replacePageContent(doc, "<p>new</p>", "Renamed");
    expect(html(doc).titleHTML).toBe("Renamed");
  });

  it("replaces only the title when no body is given", () => {
    const doc = pageDoc("<p>keep</p>", "Design");
    replacePageContent(doc, null, "Renamed");
    const out = html(doc);
    expect(out.titleHTML).toBe("Renamed");
    expect(out.contentHTML.match(/keep/g)).toHaveLength(1);
  });

  it("merges into a stale client copy without duplicating content", () => {
    const server = pageDoc("<p>old</p>", "Design");
    const stale = new Y.Doc();
    Y.applyUpdate(stale, Y.encodeStateAsUpdate(server));

    replacePageContent(server, "<p>new</p>");
    Y.applyUpdate(stale, Y.encodeStateAsUpdate(server));

    const out = html(stale);
    expect(out.contentHTML.match(/new/g)).toHaveLength(1);
    expect(out.contentHTML).not.toContain("old");
    expect(out.titleHTML).toBe("Design");
  });
});

describe("writePageContent", () => {
  it("writes into the stored state when the page isn't loaded", async () => {
    const stored = pageDoc("<p>old</p>", "Design");
    const result = await writePageContent(fakeInstance(), {
      pageId: PAGE_ID,
      descriptionHTML: "<p>new</p>",
      storedBinary: convertBinaryDataToBase64String(Y.encodeStateAsUpdate(stored)),
    });
    expect(result.loaded).toBe(false);
    expect(result.description_html).toContain("new");

    // the old content is deleted, not rebuilt, so the stored copy merges cleanly
    Y.applyUpdate(stored, new Uint8Array(convertBase64StringToBinaryData(result.description_binary)));
    expect(html(stored).contentHTML).not.toContain("old");
  });

  it("builds a new state for a page with no stored binary", async () => {
    const result = await writePageContent(fakeInstance(), { pageId: PAGE_ID, descriptionHTML: "<p>first</p>" });
    expect(result.description_html).toContain("first");
  });

  it("keeps the body on a rename of a page with no stored binary", async () => {
    const result = await writePageContent(fakeInstance(), {
      pageId: PAGE_ID,
      name: "Renamed",
      storedHTML: "<p>keep me</p>",
      storedName: "Design",
    });
    expect(result.description_html).toContain("keep me");
    const doc = new Y.Doc();
    Y.applyUpdate(doc, new Uint8Array(convertBase64StringToBinaryData(result.description_binary)));
    expect(html(doc).titleHTML).toBe("Renamed");
    expect(html(doc).contentHTML.match(/keep me/g)).toHaveLength(1);
  });

  it("ignores the stored HTML when the page is open", async () => {
    const loaded = pageDoc("<p>unsaved edit</p>", "Design");
    const result = await writePageContent(fakeInstance({ [PAGE_ID]: loaded }), {
      pageId: PAGE_ID,
      name: "Renamed",
      storedHTML: "<p>stale</p>",
    });
    expect(result.description_html).toContain("unsaved edit");
    expect(result.description_html).not.toContain("stale");
  });

  it("edits the loaded doc in place when the page is open", async () => {
    const loaded = pageDoc("<p>old</p>", "Design");
    const updates: Uint8Array[] = [];
    loaded.on("update", (update: Uint8Array) => updates.push(update));

    const result = await writePageContent(fakeInstance({ [PAGE_ID]: loaded }), {
      pageId: PAGE_ID,
      descriptionHTML: "<p>new</p>",
      storedBinary: convertBinaryDataToBase64String(Y.encodeStateAsUpdate(pageDoc("<p>ignored</p>"))),
    });
    expect(result.loaded).toBe(true);
    expect(html(loaded).contentHTML).toContain("new");
    expect(result.description_html).not.toContain("ignored");
    expect(updates).toHaveLength(1);
  });
});

describe("SquadronPageContentController", () => {
  let server: Server;
  let url: string;

  beforeAll(async () => {
    const { registerController } = await import("@plane/decorators");
    const { SquadronPageContentController, PAGE_CONTENT_MEDIA_TYPE } =
      await import("@/squadron/page-content.controller");
    const app = express();
    app.use(express.json());
    const router = express.Router();
    registerController(router, SquadronPageContentController, [fakeInstance()]);
    app.use("/live", router);
    server = app.listen(0);
    url = `http://127.0.0.1:${(server.address() as AddressInfo).port}/live/squadron/pages/${PAGE_ID}/content/`;
    process.env.MEDIA_TYPE = PAGE_CONTENT_MEDIA_TYPE;
  });
  afterAll(() => server.close());

  const post = (body: unknown, headers: Record<string, string> = {}) =>
    fetch(url, {
      method: "POST",
      headers: { "content-type": process.env.MEDIA_TYPE!, "live-server-secret-key": SECRET, ...headers },
      body: JSON.stringify(body),
    });

  it("refuses a request without the secret", async () => {
    const res = await post({ description_html: "<p>x</p>" }, { "live-server-secret-key": "wrong" });
    expect(res.status).toBe(401);
  });

  it("rejects a body with nothing to write", async () => {
    expect((await post({ description_binary: null })).status).toBe(400);
  });

  it("accepts a state larger than the app-wide JSON limit", async () => {
    const big = `<p>${"a".repeat(300_000)}</p>`;
    const res = await post({ description_html: big });
    expect(res.status).toBe(200);
    expect(((await res.json()) as { description_html: string }).description_html).toContain("aaaa");
  });
});

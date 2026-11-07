/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { afterEach, describe, expect, inject, it } from "vitest";
import * as Y from "yjs";
import { openPage, type PageEditor } from "../src/collab";
import { ApiClient, type Page } from "../src/plane";

const stack = inject("stack");
const api = new ApiClient(stack.apiKey, stack.workspaceSlug);
const pages = `projects/${stack.projectId}/pages/`;

const createPage = (name: string, html: string) => api.call<Page>("POST", pages, { name, description_html: html });

async function until<T>(
  read: () => Promise<T>,
  ready: (value: T) => boolean,
  deadline = Date.now() + 20_000
): Promise<T> {
  const value = await read();
  if (ready(value) || Date.now() > deadline) return value;
  await new Promise((resolve) => setTimeout(resolve, 500));
  return until(read, ready, deadline);
}

describe("project pages across the API and live", () => {
  let editor: PageEditor | undefined;
  afterEach(() => editor?.close());

  it("opens a page created over the API in the editor", async () => {
    const page = await createPage("Created over the API", "<p>written by the API</p>");
    editor = await openPage(stack, page.id);
    expect(editor.body()).toContain("written by the API");
  });

  it("puts an API update into an open editor in place", async () => {
    const page = await createPage("Updated while open", "<p>before</p>");
    editor = await openPage(stack, page.id);
    const doc = editor.doc;

    const updated = await api.call<Page>("PATCH", `${pages}${page.id}/`, { description_html: "<p>after</p>" });

    expect(updated.description_html).toContain("after");
    const body = await editor.waitFor(editor.body, (value) => value.includes("after"));
    expect(body).not.toContain("before");
    expect(editor.doc).toBe(doc);
  });

  it("renames a page in the editor's title and the API", async () => {
    const page = await createPage("Old name", "<p>body stays</p>");
    editor = await openPage(stack, page.id);

    await api.call<Page>("PATCH", `${pages}${page.id}/`, { name: "New name" });

    await editor.waitFor(editor.title, (value) => value.includes("New name"));
    expect(editor.body()).toContain("body stays");
    expect((await api.call<Page>("GET", `${pages}${page.id}/`)).name).toBe("New name");
  });

  it("saves what the editor types back to the API", async () => {
    const page = await createPage("Typed into", "<p>first line</p>");
    editor = await openPage(stack, page.id);

    const paragraph = new Y.XmlElement("paragraph");
    paragraph.insert(0, [new Y.XmlText("typed in the editor")]);
    editor.doc.getXmlFragment("default").push([paragraph]);

    const saved = await until(
      () => api.call<Page>("GET", `${pages}${page.id}/`),
      (value) => value.description_html.includes("typed in the editor")
    );
    expect(saved.description_html).toContain("typed in the editor");
    expect(saved.description_html).toContain("first line");
  });
});

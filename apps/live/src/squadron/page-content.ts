/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { Hocuspocus } from "@hocuspocus/server";
import * as Y from "yjs";
import { TiptapTransformer } from "@hocuspocus/transformer";
import type { AnyExtension, JSONContent } from "@tiptap/core";
import {
  TITLE_EDITOR_EXTENSIONS,
  convertBase64StringToBinaryData,
  generateTitleProsemirrorJson,
  getAllDocumentFormatsFromDocumentEditorBinaryData,
  getBinaryDataFromDocumentEditorHTMLString,
} from "@plane/editor";
import type { TDocumentPayload } from "@plane/types";

/**
 * Replaces the page body and/or title inside an existing Y.Doc; a part not given is left alone.
 * Deleting in place, rather than building a new doc, lets stale client copies merge cleanly.
 * Runs with no transaction origin, so Hocuspocus broadcasts it but doesn't store it.
 */
export const replacePageContent = (doc: Y.Doc, descriptionHTML?: string | null, name?: string | null): void => {
  doc.transact(() => {
    if (descriptionHTML != null) {
      const body = doc.getXmlFragment("default");
      body.delete(0, body.length);
      Y.applyUpdate(doc, getBinaryDataFromDocumentEditorHTMLString(descriptionHTML));
    }
    if (name != null) {
      const title = doc.getXmlFragment("title");
      title.delete(0, title.length);
      const titleJSON = (generateTitleProsemirrorJson as (text: string) => JSONContent)(name);
      const titleDoc = TiptapTransformer.toYdoc(titleJSON, "title", TITLE_EDITOR_EXTENSIONS as AnyExtension[]);
      Y.applyUpdate(doc, Y.encodeStateAsUpdate(titleDoc));
    }
  });
};

export type TPageContentInput = {
  pageId: string;
  descriptionHTML?: string | null;
  name?: string | null;
  // base64 state the API holds, used when no live copy of the page is loaded
  storedBinary?: string | null;
};

export type TPageContentResult = TDocumentPayload & { loaded: boolean };

const getLoadedDocument = async (instance: Hocuspocus, pageId: string): Promise<Y.Doc | null> => {
  const loading = instance.loadingDocuments.get(pageId);
  if (loading) {
    try {
      return await loading;
    } catch {
      return null;
    }
  }
  const doc = instance.documents.get(pageId);
  return doc && !doc.isLoading ? doc : null;
};

/** Writes new content into the page's live doc if loaded, otherwise into the stored state. */
export const writePageContent = async (
  instance: Hocuspocus,
  { pageId, descriptionHTML, name, storedBinary }: TPageContentInput
): Promise<TPageContentResult> => {
  const loaded = await getLoadedDocument(instance, pageId);
  const doc = loaded ?? new Y.Doc();
  if (!loaded && storedBinary) Y.applyUpdate(doc, new Uint8Array(convertBase64StringToBinaryData(storedBinary)));

  replacePageContent(doc, descriptionHTML, name);

  const { contentBinaryEncoded, contentHTML, contentJSON } = getAllDocumentFormatsFromDocumentEditorBinaryData(
    Y.encodeStateAsUpdate(doc),
    false
  );
  return {
    description_binary: contentBinaryEncoded,
    description_html: contentHTML,
    description_json: contentJSON,
    loaded: loaded !== null,
  };
};

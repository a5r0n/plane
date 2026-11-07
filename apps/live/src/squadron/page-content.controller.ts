/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { Hocuspocus } from "@hocuspocus/server";
import type { Request, Response } from "express";
import express from "express";
import { z } from "zod";
import { Controller, Middleware, Post } from "@plane/decorators";
import { logger } from "@plane/logger";
import { requireSecretKey } from "@/lib/auth-middleware";
import { writePageContent } from "./page-content";

// own media type, so the app-wide 100kb JSON parser leaves large page states to this route
export const PAGE_CONTENT_MEDIA_TYPE = "application/vnd.squadron.page-content+json";

const bodySchema = z
  .object({
    description_html: z.string().nullish(),
    name: z.string().nullish(),
    description_binary: z.string().nullish(),
    stored_html: z.string().nullish(),
    stored_name: z.string().nullish(),
  })
  .refine((body) => body.description_html != null || body.name != null, "Nothing to write");

/** Lets the API replace a project page's content in place, reaching any open editor. */
@Controller("/squadron/pages")
export class SquadronPageContentController {
  [key: string]: unknown;
  private readonly hocusPocusServer: Hocuspocus;

  constructor(hocusPocusServer: Hocuspocus) {
    this.hocusPocusServer = hocusPocusServer;
  }

  @Post("/:pageId/content/")
  @Middleware(express.json({ type: PAGE_CONTENT_MEDIA_TYPE, limit: "20mb" }))
  @Middleware(requireSecretKey)
  async writeContent(req: Request, res: Response) {
    const pageId = req.params.pageId;
    if (!z.string().uuid().safeParse(pageId).success) return res.status(400).json({ message: "Invalid page id" });
    const body = bodySchema.safeParse(req.body);
    if (!body.success) return res.status(400).json({ message: "Validation error" });
    try {
      const result = await writePageContent(this.hocusPocusServer, {
        pageId,
        descriptionHTML: body.data.description_html,
        name: body.data.name,
        storedBinary: body.data.description_binary,
        storedHTML: body.data.stored_html,
        storedName: body.data.stored_name,
      });
      return res.status(200).json(result);
    } catch (error) {
      logger.error("SQUADRON_PAGE_CONTENT: failed to write page content", error);
      return res.status(500).json({ message: "Internal server error." });
    }
  }
}

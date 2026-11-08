/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TStep } from "./types";

type TRow = { verb?: string; old_value?: string | null; new_value?: string | null; comment?: string };
type TParsed = Partial<TStep> | Partial<TStep>[] | null;

const parse = (value?: string | null): TParsed => {
  if (!value) return null;
  try {
    return JSON.parse(value) as TParsed;
  } catch {
    return null;
  }
};

/** One `field: step` activity row as text: what the write did, named by step title. */
export const describeStepActivity = (row: TRow): { text: string; title?: string; note?: string } => {
  const old = parse(row.old_value);
  const next = parse(row.new_value);
  if (Array.isArray(old) || Array.isArray(next)) {
    if (row.comment?.startsWith("reordered")) return { text: "reordered the path" };
    return { text: `replaced the path (${Array.isArray(next) ? next.length : 0} steps)` };
  }
  if (row.verb === "created" && next) return { text: "added step", title: next.title };
  if (row.verb === "deleted" && old) return { text: "removed step", title: old.title };
  if (old && next) {
    const note = next.note || undefined;
    if (old.status !== next.status) {
      if (next.status === "done") return { text: "finished", title: next.title, note };
      if (next.status === "failed") return { text: "marked failed", title: next.title, note };
      if (next.status === "skipped") return { text: "skipped", title: next.title, note };
      return { text: "reopened", title: next.title };
    }
    if (old.not_before && !next.not_before) return { text: "started now", title: next.title };
    return { text: "edited step", title: next.title };
  }
  return { text: row.comment ?? "updated steps" };
};

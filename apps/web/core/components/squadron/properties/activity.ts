/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

type TRow = { comment?: string; old_value?: string | null; new_value?: string | null };

export type TPropertyActivity = { verb: "set" | "changed" | "cleared"; name: string; from?: string; to?: string };

/** A `custom_fields` activity row as words: set, changed or cleared, and the property's name. */
export const describePropertyActivity = (row: TRow): TPropertyActivity => {
  const name = (row.comment ?? "").replace(/^updated /, "");
  const from = row.old_value ?? undefined;
  const to = row.new_value ?? undefined;
  if (to === undefined) return { verb: "cleared", name, from };
  if (from === undefined) return { verb: "set", name, to };
  return { verb: "changed", name, from, to };
};

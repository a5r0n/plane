/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/** Whether /browse/<KEY-N> shows an item of the project with this identifier. */
export function isBrowsingProject(workItemKey: string | string[] | undefined, identifier: string | undefined): boolean {
  if (!workItemKey || !identifier) return false;
  const key = workItemKey.toString().toUpperCase();
  const dash = key.lastIndexOf("-");
  return dash > 0 && key.slice(0, dash) === identifier.toUpperCase();
}

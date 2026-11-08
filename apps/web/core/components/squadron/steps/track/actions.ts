/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TStep } from "../types";

export type TStepAction =
  | "done"
  | "failed"
  | "skip"
  | "pending"
  | "edit"
  | "insert-above"
  | "insert-below"
  | "move-up"
  | "move-down"
  | "delete";

export const ACTION_LABELS: Record<TStepAction, string> = {
  done: "Mark done",
  failed: "Mark failed…",
  skip: "Skip",
  pending: "Back to pending",
  edit: "Edit (title, detail, actor)",
  "insert-above": "Insert step above",
  "insert-below": "Insert step below",
  "move-up": "Move up",
  "move-down": "Move down",
  delete: "Delete",
};

/** The row menu for a step at index of count. */
export const stepActions = (step: Pick<TStep, "status">, index: number, count: number): TStepAction[] => {
  const statuses: TStepAction[] =
    step.status === "pending"
      ? ["done", "failed", "skip"]
      : step.status === "failed"
        ? ["pending", "skip"]
        : ["pending"];
  const moves: TStepAction[] = [];
  if (index > 0) moves.push("move-up");
  if (index < count - 1) moves.push("move-down");
  return [...statuses, "edit", "insert-above", "insert-below", ...moves, "delete"];
};

/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

export type TStepStatus = "pending" | "done" | "failed" | "skipped";

export type TStep = {
  id: string;
  issue: string;
  title: string;
  detail: string;
  actor: string | null;
  status: TStepStatus;
  note: string;
  sort_order: number;
  not_before: string | null;
  created_at: string;
  updated_at: string;
};

export type TStepInput = Partial<Pick<TStep, "title" | "detail" | "actor" | "status" | "note" | "not_before">>;

export type TCurrentStep = Pick<TStep, "id" | "title" | "status" | "not_before" | "actor">;

// What list rows carry as `step_summary` (null when the item has no steps).
export type TStepSummary = { done: number; total: number; current: TCurrentStep | null };

// How a step reads to the viewer: their turn (amber), failed (red), waiting (grey), or neutral.
export type TStepTone = "turn" | "failed" | "waiting" | "neutral";
